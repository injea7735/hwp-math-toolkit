"""
쎈수학 미적분Ⅰ "문제.pdf"에서 유형별로 문제를 잘라낸다.

다른 쎈수학 과목(대수/미적분2/확률과 통계)과 같은 색상 마커 체계를 쓰지만
(초록 유형 알약, 빨강 대표문제 알약, 초록 굵은 4자리 번호), 그 과목들과
달리 유형 제목·대표문제 번호·정답을 대조 검증할 HWP "대표문제" 인덱스
자료가 없다. 대신 이 책은 각 대단원 시작부에 유형 제목이 일반 텍스트로
인쇄된 목차(TOC) 페이지가 있어서(pdf_mi1_toc_parse.py가 뽑는다), 그
순서대로 유형 이름을 매칭한다 - 대표문제 번호/정답은 이 자료에 없으므로
본문에서 읽은 값을 그대로 쓰고(범위 검증 없이), 소단원 경계는 "지금까지
매칭한 유형 수가 이 소단원의 총 유형 수를 넘으면 다음 소단원"으로 판단한다
(다른 과목들의 롤오버 로직과 동일).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

from pdf_sen_extract import (
    DPI, _find_green_boxes, _find_red_boxes, _is_concept_heading,
    _is_digit_fragment, _ocr_digits, _page_array, _save_trimmed,
)

_TITLE_MATCH_WINDOW = 6  # 몇 칸 앞까지(같은 소단원 안에서만) 재동기화를 시도할지
_TITLE_MATCH_THRESHOLD = 0.5
_STRIP_RE = re.compile(r'[^가-힣0-9]')


def _norm_title(s: str) -> str:
    return _STRIP_RE.sub('', s)


def _title_similarity(a: str, b: str) -> float:
    """글자 집합 겹침 비율(순서 무시) - OCR이 띄어쓰기/조사를 흘리거나
    수식 기호를 깨뜨려도 한글 핵심 어절이 남아 있으면 높게 나온다."""
    a, b = _norm_title(a), _norm_title(b)
    if not a or not b:
        return 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return sum(1 for c in shorter if c in longer) / len(shorter)


def _ocr_pill_title(page, box) -> str:
    """유형 알약 자체(숫자)는 못 읽지만, 바로 오른쪽에 일반 텍스트로 인쇄된
    제목은 잘 읽힌다 - pdf_mi1_toc_parse.py의 목차 OCR과 같은 원리."""
    x, y, w, h = box[:4]
    rect = fitz.Rect((x + w) * 72 / DPI, y * 72 / DPI, (x + w + 380) * 72 / DPI, (y + h) * 72 / DPI)
    pix = page.get_pixmap(clip=rect, dpi=400)
    img = Image.frombuffer('RGB', (pix.width, pix.height), pix.samples, 'raw', 'RGB', 0, 1)
    return pytesseract.image_to_string(img, lang='kor', config='--psm 7').strip()


def _is_daepyo_pill_mi1(box) -> bool:
    """원래 기준(r>g+80)은 이 책의 대표문제 알약 중 일부(예: (219,141,79)
    r-g=78, 심지어 (239,197,70) r-g=42인 것도 실존 - 육안으로 직접 대조
    확인함)를 놓친다. r-b는 이 책에서 실측 최소 127로 여유가 커서 그대로
    두고, r-g만 20까지 낮춘다."""
    x, y, w, h, (r, g, b) = box
    return 110 <= w <= 160 and 22 <= h <= 36 and r > g + 20 and r > b + 100


def _is_type_pill_mi1(box) -> bool:
    """대수/미적분2/확통과 같은 크기대이지만, 이 책의 유형 알약은 더 청록색
    쪽으로 치우쳐 찍혀서(예: (48,168,164) - 원래 기준 g>b+12를 통과 못함)
    파란색 성분 조건을 완화해야 한다. _find_green_boxes의 마스크 단계에서
    이미 g>=b가 보장되므로 추가로 b를 따로 견제할 필요는 크지 않다.

    가로폭 하한을 원래(50)보다 좁혀야 한다 - 유형 제목 옆의 작은 "개념
    NN-N" 참조 배지(56×26 안팎)가 원래 범위(50~80×26~42)에 걸쳐 있어서
    진짜 유형 알약(이 책에서는 실측 63~64×34~36으로 훨씬 좁게 몰려 있다)과
    혼동됐다."""
    x, y, w, h, (r, g, b) = box
    return 58 <= w <= 72 and 30 <= h <= 40 and g > r + 20


def _cluster_digits_mi1(fragments):
    """pdf_sen_extract._cluster_digits와 같은 목적이지만, 이 책에서는 같은
    줄 안의 획 4개끼리도 y좌표가 안티에일리어싱 때문에 1px씩 들쭉날쭉한
    경우가 흔하다(예: 728/729/729/729). 원래 함수는 (y, x) 튜플로 그대로
    정렬해서, 그 1px 차이 때문에 오른쪽 획이 왼쪽 획들보다 먼저 정렬되면
    이후 "왼쪽에서 오른쪽으로만 이어붙인다"는 가정이 깨져 그룹이 통째로
    안 만들어진다 - 실제로 겪음(번호 마커가 아예 안 잡혀서 문제 여러 개가
    한 크롭에 뭉침). y로 먼저 "같은 줄" 그룹을 확정(y 간격이 4px 넘게
    벌어지면 새 줄로 간주)한 뒤 그 줄 안에서만 x로 정렬하면 이 문제가
    없다 - 단순히 y를 특정 배수로 반올림(버킷팅)하는 방식은 728/729처럼
    반올림 경계선에 걸치는 값에서 여전히 다른 버킷으로 갈라지는 걸
    실제로 확인해서 버렸다."""
    by_y = sorted(fragments, key=lambda b: b[1])
    rows: list[list] = []
    for f in by_y:
        if rows and f[1] - rows[-1][-1][1] <= 4:
            rows[-1].append(f)
        else:
            rows.append([f])
    frags = [f for row in rows for f in sorted(row, key=lambda b: b[0])]
    used = [False] * len(frags)
    groups = []
    for i, f in enumerate(frags):
        if used[i]:
            continue
        x0, y0, w0, h0, _ = f
        group = [f]
        used[i] = True
        cy = y0 + h0 / 2
        last_x1 = x0 + w0
        for j in range(i + 1, len(frags)):
            if used[j]:
                continue
            x1, y1, w1, h1, _ = frags[j]
            if abs((y1 + h1 / 2) - cy) < 6 and 0 <= x1 - last_x1 <= 8:
                group.append(frags[j])
                used[j] = True
                last_x1 = x1 + w1
        if len(group) == 4:
            gx0 = min(g[0] for g in group)
            gy0 = min(g[1] for g in group)
            gx1 = max(g[0] + g[2] for g in group)
            gy1 = max(g[1] + g[3] for g in group)
            groups.append((gx0, gy0, gx1 - gx0, gy1 - gy0))
    return groups


def _page_markers_mi1(page):
    arr = _page_array(page)
    W = arr.shape[1]
    markers = []
    green_boxes = _find_green_boxes(arr)
    for b in green_boxes:
        if _is_type_pill_mi1(b):
            x = b[0]
            column = 0 if x < W / 2 else 1
            markers.append(('type_pill', b, column))
    for b in _find_red_boxes(arr):
        x = b[0]
        column = 0 if x < W / 2 else 1
        if _is_daepyo_pill_mi1(b):
            markers.append(('daepyo_pill', b, column))
        elif _is_concept_heading(b):
            markers.append(('heading', b, column))

    digit_frags = [b for b in green_boxes if _is_digit_fragment(b)]
    for gx0, gy0, gw, gh in _cluster_digits_mi1(digit_frags):
        column = 0 if gx0 < W / 2 else 1
        markers.append(('number', (gx0, gy0, gw, gh, None), column))

    markers.sort(key=lambda m: (m[2], m[1][1]))
    return markers


@dataclass
class Mi1Problem:
    section_name: str
    subsection_name: str
    type_no: str
    type_title: str
    number: str | None
    is_daepyo: bool
    page_index: int
    image_path: str


def extract_problems(
    pdf_path: str, out_dir: str,
    subsection_order: list[tuple[str, str]],
    toc: dict[str, list[tuple[str, str]]],
    page_range: range | None = None,
) -> tuple[list[Mi1Problem], list[str]]:
    """페이지를 (컬럼0, 컬럼1) 순서로, 실제 읽는 순서 그대로 훑는다.

    유형 알약과 그 대표문제 알약이 항상 같은 페이지 안에 있지는 않다 -
    유형 알약이 어떤 컬럼의 맨 아래에 나오고 그 대표문제는 다음 페이지의
    같은 컬럼 맨 위에 이어지는 경우가 실제로 있다(예: p33 col0의 유형
    알약 + p34 col0의 대표문제). 페어링 검증을 그 페이지 안에서만 하면
    이런 유형 알약은 "같은 페이지 안에 대표문제가 없다"고 오판해 통째로
    버려지고, 그 뒤로는 순번이 한 칸씩 밀려 마지막 소단원들이 통째로
    다른 소단원 이름으로 잘못 라벨링되는 심각한 문제가 생긴다(실제로
    겪음: 이 보정 없이 돌렸더니 148개 중 32개 유형 알약이 사라지고
    마지막 두 소단원이 통째로 누락됨). 그래서 페어링 검증만 다음 페이지
    같은 컬럼의 맨 앞 마커까지 한 페이지 앞서 내다본다 - 읽는 순서 자체는
    페이지 단위 그대로 유지한다(컬럼0 다음 컬럼1, 그 다음 페이지).

    크롭 경계는 여전히 페이지 단위로 계산한다(마커가 다음 페이지에 있으면
    이번 페이지 바닥까지만 잘라 저장한다) - 문제 내용이 실제로 페이지
    경계를 가로질러 이어지는 극소수 케이스는 아래쪽이 잘릴 수 있지만,
    이건 유형이 통째로 사라지는 것보다 훨씬 가벼운 손실이고 검토 시
    육안으로 바로 눈에 띈다.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    stem = Path(pdf_path).stem
    pages = list(page_range if page_range is not None else range(doc.page_count))

    page_col_markers: dict[tuple[int, int], list[tuple]] = {}
    page_dims: dict[int, tuple[float, float]] = {}
    for pno in pages:
        page = doc[pno]
        page_dims[pno] = (page.rect.width, page.rect.height)
        markers = _page_markers_mi1(page)
        by_col: dict[int, list] = {0: [], 1: []}
        for kind, box, column in markers:
            by_col[column].append((kind, box))
        for column in (0, 1):
            page_col_markers[(pno, column)] = sorted(by_col[column], key=lambda m: m[1][1])

    def _has_daepyo_before_next_type(pno: int, column: int, idx: int) -> bool:
        col_markers = page_col_markers[(pno, column)]
        for j in range(idx + 1, len(col_markers)):
            if col_markers[j][0] == 'type_pill':
                return False
            if col_markers[j][0] == 'daepyo_pill':
                return True
        # 이 페이지 안에서 못 정했으면 다음 페이지 같은 컬럼의 맨 앞을 본다
        # (대표문제가 페이지 경계 바로 다음에서 시작하는 경우).
        next_markers = page_col_markers.get((pno + 1, column))
        if next_markers:
            return next_markers[0][0] == 'daepyo_pill'
        return False

    results: list[Mi1Problem] = []
    warnings: list[str] = []
    sub_idx = 0
    next_type_no = 1
    current_type_no: str | None = None
    current_type_title: str | None = None

    def entries_for(idx: int) -> list[tuple[str, str]]:
        return toc[subsection_order[idx][1]]

    def _window(start_sub_idx: int, start_type_no: int, n: int) -> list[tuple[int, int]]:
        """(sub_idx, type_no) 쌍을 최대 n개 낸다 - 지금 소단원 안에서만 찾는다.

        처음엔 다음 소단원까지 넘어가며 찾게 했었는데, 한 소단원 안에서
        연속으로 여러 유형 알약이 안 걸리면(윈도우 크기 이상으로 밀리면)
        다음 소단원의 앞쪽 유형과 우연히 제목이 비슷해 보여(임계값을
        가까스로 넘겨) 엉뚱한 소단원으로 잘못 건너뛰는 사고가 실제로
        났다(도함수의 활용⑶ 내용이 부정적분 유형으로 잘못 붙음). 소단원
        전환 자체는 원래의 위치 기반 롤오버 판정(type_no > len(entries))
        하나만 믿는 게 안전하다 - 그 판정은 이 페이지 제목이 아니라 "이번
        소단원 유형을 다 썼는가"만 보므로 오탐 여지가 훨씬 적다."""
        entries = entries_for(start_sub_idx)
        return [
            (start_sub_idx, tn)
            for tn in range(start_type_no, min(start_type_no + n, len(entries) + 1))
        ]

    def _best_match(real_title: str, candidates: list[tuple[int, int]]) -> tuple[int, int] | None:
        best = None
        best_sim = 0.0
        for si, tn in candidates:
            _, title = entries_for(si)[tn - 1]
            sim = _title_similarity(title, real_title)
            if sim > best_sim:
                best_sim, best = sim, (si, tn)
        return best if best is not None and best_sim >= _TITLE_MATCH_THRESHOLD else None

    for pno in pages:
        page = doc[pno]
        W, H = page_dims[pno]

        for column in (0, 1):
            col_markers = [
                m for i, m in enumerate(page_col_markers[(pno, column)])
                if m[0] != 'type_pill' or _has_daepyo_before_next_type(pno, column, i)
            ]

            for i, (kind, box) in enumerate(col_markers):
                y0 = box[1]
                y1 = col_markers[i + 1][1][1] if i + 1 < len(col_markers) else H * DPI / 72

                if kind == 'heading':
                    continue

                if kind == 'type_pill':
                    real_title = _ocr_pill_title(page, box)
                    resolved = (
                        _best_match(real_title, _window(sub_idx, next_type_no, _TITLE_MATCH_WINDOW))
                        if real_title else None
                    )
                    if resolved is not None:
                        if resolved != (sub_idx, next_type_no):
                            got_name = subsection_order[resolved[0]][1]
                            warnings.append(
                                f'p{pno} col{column} 재동기화: 위치상 예상='
                                f'{subsection_order[sub_idx][1]}유형{next_type_no} -> '
                                f'실제 제목 매칭={got_name}유형{resolved[1]}'
                            )
                        sub_idx, type_no = resolved
                    else:
                        type_no = next_type_no
                        if type_no > len(entries_for(sub_idx)):
                            # 지금 소단원 안에서는 못 찾았다 - 다음 소단원으로
                            # 진짜 넘어간 게 맞는지, 그 제목으로 한 번 더
                            # 확인한다(안 그러면 지금 소단원의 뒷부분 유형이
                            # 여러 개 연달아 안 걸렸을 때 다음 소단원으로
                            # 잘못 새는 사고가 난다 - 실제로 겪음).
                            next_confirmed = (
                                real_title and sub_idx + 1 < len(subsection_order)
                                and _best_match(real_title, _window(sub_idx + 1, 1, _TITLE_MATCH_WINDOW))
                            )
                            if next_confirmed:
                                sub_idx, type_no = next_confirmed
                            elif current_type_no is not None:
                                # 확인이 안 되면 소단원을 넘기지 않는다 - 지금
                                # 유형에 계속 붙이는 쪽이 엉뚱한 소단원으로
                                # 새는 것보다 낫다.
                                continue
                            elif sub_idx + 1 < len(subsection_order):
                                sub_idx += 1
                                type_no = 1
                            else:
                                continue
                    entries = entries_for(sub_idx)
                    current_type_no, current_type_title = entries[type_no - 1]
                    next_type_no = type_no + 1
                    continue

                if current_type_no is None:
                    continue

                if y1 <= y0:
                    continue

                x0, x1 = (0, W / 2) if column == 0 else (W / 2, W)
                y0_pt = y0 * 72 / DPI
                y1_pt = y1 * 72 / DPI
                clip = fitz.Rect(x0, y0_pt, x1, y1_pt)

                is_daepyo = kind == 'daepyo_pill'
                ocr = _ocr_digits(page, box, max_w=58 if is_daepyo else None, align='left')
                digits = re.sub(r'\D', '', ocr)
                number = digits if len(digits) == 4 else None

                section_name, subsection_name = subsection_order[sub_idx]
                img_name = f'{stem}_{pno:04d}_{number or f"col{column}-{i}"}.png'
                img_path = str(Path(out_dir) / img_name)
                try:
                    pix = page.get_pixmap(clip=clip, dpi=200)
                    _save_trimmed(pix, img_path)
                except Exception as exc:
                    warnings.append(f'p{pno} col{column} 이미지 저장 실패({clip}): {exc}')
                    continue

                results.append(Mi1Problem(
                    section_name=section_name, subsection_name=subsection_name,
                    type_no=current_type_no, type_title=current_type_title,
                    number=number, is_daepyo=is_daepyo,
                    page_index=pno, image_path=img_path,
                ))

    doc.close()
    return results, warnings


MI1_SUBSECTION_ORDER = [
    ('함수의 극한과 연속', '함수의 극한'),
    ('함수의 극한과 연속', '함수의 연속'),
    ('미분', '미분계수와 도함수'),
    ('미분', '도함수의 활용 ⑴'),
    ('미분', '도함수의 활용 ⑵'),
    ('미분', '도함수의 활용 ⑶'),
    ('적분', '부정적분'),
    ('적분', '정적분'),
    ('적분', '정적분의 활용'),
]

TOC_PAGE_INDICES = [6, 42, 118]


if __name__ == '__main__':
    import sys
    from collections import Counter

    from pdf_mi1_toc_parse import parse_toc_pages

    pdf_path = sys.argv[1]
    out_dir = sys.argv[2]

    toc = parse_toc_pages(pdf_path, TOC_PAGE_INDICES, [name for _, name in MI1_SUBSECTION_ORDER])
    problems, warnings = extract_problems(pdf_path, out_dir, MI1_SUBSECTION_ORDER, toc)
    with open('mi1_sen_extract_log.txt', 'w', encoding='utf-8') as f:
        f.write(f'총 문제 수: {len(problems)}\n')
        f.write(f'대표문제 수: {sum(1 for p in problems if p.is_daepyo)}\n')
        by_sub = Counter(p.subsection_name for p in problems)
        f.write(f'소단원별: {dict(by_sub)}\n')
        f.write(f'경고 {len(warnings)}건:\n')
        for w in warnings:
            f.write(f'  {w}\n')
    print('done, see mi1_sen_extract_log.txt')
