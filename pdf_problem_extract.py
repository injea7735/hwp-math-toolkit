"""
"내신고쟁이" 계열 PDF 유형서(대수/미적분Ⅰ/확률과 통계 등)에서 문제를
개별 이미지로 잘라낸다.

이 시리즈 PDF는 수식이 커스텀 폰트 글리프로 그려져 있어(PUA 코드포인트를
과목마다 다른 폰트가 재정의) 텍스트로 뽑으면 수식 부분이 깨진다. 그래서
문제 본문은 이미지로 통째로 저장하고, 아래 것들만 신뢰도 높게 구조화한다:

  - 대단원 경계: "지수함수와\n로그함수" 처럼 큰 폰트(>=33pt)로 된 도입부
    페이지 개수를 세어서, 이미 교육과정 기준으로 심어둔 Section 순서와
    맞춘다(제목 텍스트 자체는 안 믿는다 - 레이아웃이 불안정했음).
  - 난이도 단계: 페이지에 "STEP 핵심 유형"/"심화 유형"/"최고난도 유형" 문구가
    반복해서 러닝헤더로 나온다 - 다음 단계가 나올 때까지 유지되는 상태값.
  - 문제 경계: 21pt 'DINCondensed-Bold' 폰트로 된 3자리 문제 번호("00"+숫자
    두 조각으로 쪼개져 나옴). 2단 레이아웃이라 왼쪽 열을 위에서 아래로 다
    읽고 오른쪽 열로 넘어가는 순서로 정렬한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz

DIVIDER_MIN_SIZE = 33.0
DIVIDER_FONT = 'JalnanGothic'  # 대단원 도입부 큰 제목에만 쓰이는 폰트.
# 60pt 'DINCondensed-Bold' 로 된 소단원 번호("01","02"...)도 크기만 보면
# 걸리기 때문에 폰트까지 같이 확인해야 진짜 대단원 경계만 잡힌다.
NUMBER_FONT = 'DINCondensed-Bold'
NUMBER_MIN_SIZE = 18.0
NUMBER_MAX_SIZE = 25.0  # 소단원 번호(60pt)와 구분하기 위한 상한

_TIER_PATTERNS = [
    ('핵심 유형', re.compile(r'핵심\s*유형')),
    ('심화 유형', re.compile(r'심화\s*유형')),
    ('최고난도 유형', re.compile(r'최고난도\s*유형')),
]


@dataclass
class ExtractedProblem:
    number: str          # 예: "001"
    section_index: int   # 몇 번째 대단원인지 (0부터)
    tier_name: str | None
    page_index: int
    image_path: str
    text: str


def _iter_spans(page):
    d = page.get_text('dict')
    for block in d['blocks']:
        if 'lines' not in block:
            continue
        for line in block['lines']:
            for s in line['spans']:
                yield s


def _detect_tier(page) -> str | None:
    text = page.get_text()
    for name, pat in _TIER_PATTERNS:
        if pat.search(text):
            return name
    return None


def _is_divider_page(page) -> bool:
    for s in _iter_spans(page):
        if s['size'] >= DIVIDER_MIN_SIZE and s['font'] == DIVIDER_FONT:
            return True
    return False


def _group_number_spans(candidates: list[dict], page_width: float):
    """숫자 조각 span들을 마커별로 묶어 (번호문자열, bbox, column) 리스트로 낸다.

    번호는 "0으로 채워진 부분"과 "실제 숫자 부분"이 별도 span으로 쪼개져
    나온다. 조각 개수·자릿수가 번호 크기에 따라 다르다("00"+"1" -> 001,
    "0"+"13" -> 013, "0"+"46" -> 046 처럼) - 정확한 조합을 가정하지 않고,
    같은 열(column)·같은 y좌표(같은 줄)에 있는 숫자 span들을 x좌표 순으로
    모아 이어붙인다. page.rect.width에 기대지 않고 순수 로직만 테스트할 수
    있도록 page_width를 인자로 받는다.
    """
    # 같은 줄(y좌표)이라도 2단 레이아웃에서는 왼쪽/오른쪽 열의 서로 다른
    # 번호일 수 있다 - 열이 다르면 절대 같은 마커로 묶지 않는다(실제 자료에서
    # "013"+"016"이 한 마커로 잘못 합쳐지는 버그가 있었다).
    groups: list[list] = []
    for s in candidates:
        y0 = s['bbox'][1]
        column = 0 if s['bbox'][0] < page_width / 2 else 1
        placed = False
        for g in groups:
            g_column = 0 if g[0]['bbox'][0] < page_width / 2 else 1
            if g_column == column and abs(g[0]['bbox'][1] - y0) < 1.0:
                g.append(s)
                placed = True
                break
        if not placed:
            groups.append([s])

    markers = []
    for g in groups:
        g.sort(key=lambda s: s['bbox'][0])
        number = ''.join(s['text'].strip() for s in g)
        x0 = min(s['bbox'][0] for s in g)
        y0 = min(s['bbox'][1] for s in g)
        x1 = max(s['bbox'][2] for s in g)
        y1 = max(s['bbox'][3] for s in g)
        column = 0 if x0 < page_width / 2 else 1
        markers.append((number, (x0, y0, x1, y1), column))

    # 왼쪽 열을 위->아래로 다 읽고, 오른쪽 열을 위->아래로 읽는 순서
    markers.sort(key=lambda m: (m[2], m[1][1]))
    return markers


def _find_number_markers(page):
    page_width = page.rect.width
    candidates = []
    for s in _iter_spans(page):
        if s['font'] != NUMBER_FONT or not (NUMBER_MIN_SIZE <= s['size'] <= NUMBER_MAX_SIZE):
            continue
        text = s['text'].strip()
        if text and re.fullmatch(r'\d+', text):
            candidates.append(s)
    return _group_number_spans(candidates, page_width)


def extract_problems(pdf_path: str, out_dir: str, section_count: int, dpi: int = 200) -> list[ExtractedProblem]:
    """대단원 개수(section_count)는 이미 curriculum 기준으로 심어둔 Section 순서와
    맞추기 위해 호출하는 쪽에서 넘겨준다(예: 대수=3)."""
    doc = fitz.open(pdf_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    results: list[ExtractedProblem] = []
    section_index = -1
    current_tier: str | None = None

    for pno in range(doc.page_count):
        page = doc[pno]

        if _is_divider_page(page):
            if section_index + 1 < section_count:
                section_index += 1
            current_tier = None
            continue

        tier = _detect_tier(page)
        if tier:
            current_tier = tier

        if section_index < 0:
            continue  # 아직 첫 대단원 도입부를 못 지남

        markers = _find_number_markers(page)
        if not markers:
            continue

        page_width = page.rect.width
        page_height = page.rect.height
        col_bounds = [(0, page_width / 2), (page_width / 2, page_width)]

        for i, (number, bbox, column) in enumerate(markers):
            y0 = bbox[1]
            # 같은 열에서 다음 마커가 나오기 전까지가 이 문제의 영역
            same_col = [m for m in markers if m[2] == column]
            same_col_sorted = sorted(same_col, key=lambda m: m[1][1])
            idx_in_col = same_col_sorted.index((number, bbox, column))
            if idx_in_col + 1 < len(same_col_sorted):
                y1 = same_col_sorted[idx_in_col + 1][1][1]
            else:
                y1 = page_height

            x0, x1 = col_bounds[column]
            clip = fitz.Rect(x0, y0, x1, y1)

            img_name = f'{Path(pdf_path).stem}_{pno:04d}_{number}.png'
            img_path = str(Path(out_dir) / img_name)
            pix = page.get_pixmap(clip=clip, dpi=dpi)
            pix.save(img_path)

            text = page.get_text(clip=clip).strip()

            results.append(ExtractedProblem(
                number=number,
                section_index=section_index,
                tier_name=current_tier,
                page_index=pno,
                image_path=img_path,
                text=text,
            ))

    doc.close()
    return results


if __name__ == '__main__':
    import sys
    pdf_path = sys.argv[1]
    out_dir = sys.argv[2]
    section_count = int(sys.argv[3])
    problems = extract_problems(pdf_path, out_dir, section_count)
    print('총 문제 수:', len(problems))
    from collections import Counter
    by_section = Counter(p.section_index for p in problems)
    by_tier = Counter(p.tier_name for p in problems)
    print('대단원별:', dict(by_section))
    print('난이도별:', dict(by_tier))
