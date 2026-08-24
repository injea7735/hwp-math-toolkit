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

from pdf_sen_extract import (
    DPI, _cluster_digits, _find_green_boxes, _find_red_boxes, _is_concept_heading,
    _is_digit_fragment, _ocr_digits, _page_array, _save_trimmed,
)


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
    for gx0, gy0, gw, gh in _cluster_digits(digit_frags):
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
                    entries = entries_for(sub_idx)
                    type_no = next_type_no
                    if type_no > len(entries):
                        if sub_idx + 1 < len(subsection_order):
                            sub_idx += 1
                            entries = entries_for(sub_idx)
                            type_no = 1
                        else:
                            current_type_no = None
                            continue
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
