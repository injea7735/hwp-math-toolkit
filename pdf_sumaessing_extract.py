"""
"수매씽" 계열 PDF 유형서(미적분Ⅱ 등)에서 문제를 추출한다.

이 시리즈는 앞서 다룬 "내신고쟁이" PDF들과 비슷하게 수식이 커스텀 폰트
글리프(Amsusic-*)로 그려져 있어 수식 자체는 텍스트로 못 뽑지만, 구조를
나타내는 요소들은 전부 일반 텍스트라 폰트/크기만으로 안정적으로 구분된다:

  - 대단원/소단원 도입부: 큰 제목(폰트 'YDVYGO14', ~47pt)과 소단원 번호
    (폰트 'DIN-Bold'/'DINBold', 50~121pt, "0"+숫자 조각으로 쪼개져 나옴)가
    도입부 페이지 1~2장에 걸쳐 나온다. 소단원 번호(01~10)는 이미
    seed_curriculum_taxonomy.py에 심어둔 실제 소단원 목록과 순서가 같다.
  - 문제 번호: 폰트 'DIN-Medium', 18pt 이상, 4자리 숫자 하나의 span으로
    깨끗하게 나온다(내신고쟁이 PDF들처럼 "00"+숫자로 쪼개지지 않음).
  - 유형 그룹 경계: "대표문제"라는 문구가 유형의 첫 문제 앞에 정확히
    붙어 나온다 - 배지 색상이 아니라 이 텍스트 자체가 신뢰할 수 있는
    경계 신호다.
  - 난이도: "Level 1/2/3" 텍스트가 문제 근처에 작게 붙어 나온다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz

PROBLEM_FONT = 'DIN-Medium'
PROBLEM_MIN_SIZE = 18.0
PROBLEM_NUMBER_RE = re.compile(r'^\d{4}$')

DIVIDER_TITLE_FONT = 'YDVYGO14'
DIVIDER_TITLE_MIN_SIZE = 40.0
DIVIDER_NUMBER_FONTS = {'DIN-Bold', 'DINBold'}
DIVIDER_NUMBER_MIN_SIZE = 40.0

LEVEL_FONT_PREFIX = 'DINPro'

# seed_curriculum_taxonomy.py의 '미적분2' 항목과 순서를 맞춘 소단원 목록.
# 소단원 도입부에서 읽은 번호(01~10)를 (대단원, 소단원) 튜플로 바로 매핑한다.
SUBSECTION_ORDER = [
    ('수열의 극한', '수열의 극한'),
    ('수열의 극한', '급수'),
    ('미분법', '지수함수와 로그함수의 미분'),
    ('미분법', '삼각함수의 미분'),
    ('미분법', '여러 가지 미분법'),
    ('미분법', '도함수의 활용 ⑴'),
    ('미분법', '도함수의 활용 ⑵'),
    ('적분법', '여러 가지 적분법'),
    ('적분법', '정적분'),
    ('적분법', '정적분의 활용'),
]


@dataclass
class SumProblem:
    number: str
    section_name: str
    subsection_name: str
    type_seq: int  # 소단원 안에서 몇 번째 유형(대표문제 그룹)인지, 1부터
    level: str | None
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


def _detect_subsection_start(page) -> int | None:
    """이 페이지가 소단원 도입부면 소단원 번호(1~10)를 반환한다."""
    has_title = any(
        s['font'] == DIVIDER_TITLE_FONT and s['size'] >= DIVIDER_TITLE_MIN_SIZE
        for s in _iter_spans(page)
    )
    if not has_title:
        return None
    # 소단원 01~09는 큰 번호가 "0"+"N" 두 글자 span으로 쪼개져 나오지만,
    # 10은 "10" 하나의 span으로 나온다 - 둘 다 받아들인다.
    digits = [
        s['text'].strip() for s in _iter_spans(page)
        if s['font'] in DIVIDER_NUMBER_FONTS and s['size'] >= DIVIDER_NUMBER_MIN_SIZE
        and re.fullmatch(r'\d{1,2}', s['text'].strip())
    ]
    if not digits:
        return None
    try:
        return int(''.join(digits))
    except ValueError:
        return None


def _find_problem_markers(page):
    page_width = page.rect.width
    markers = []
    for s in _iter_spans(page):
        text = s['text'].strip()
        if s['font'] == PROBLEM_FONT and s['size'] >= PROBLEM_MIN_SIZE and PROBLEM_NUMBER_RE.match(text):
            x0, y0, x1, y1 = s['bbox']
            column = 0 if x0 < page_width / 2 else 1
            markers.append({'number': text, 'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 'column': column})
    markers.sort(key=lambda m: (m['column'], m['y0']))
    return markers


def _find_type_starts(page) -> set:
    """'대표문제' 텍스트가 나오는 y좌표 집합을 낸다(그 바로 아래/근처 문제가
    새 유형의 시작)."""
    ys = set()
    for s in _iter_spans(page):
        if s['text'].strip() == '대표문제':
            ys.add(round(s['bbox'][1]))
    return ys


def _find_level_near(page, marker, spans_cache) -> str | None:
    """'Level '(DINPro-Medium) 라벨 span을 찾고, 바로 옆(같은 줄, x가 더 큰)
    DINPro-Bold 숫자 span을 그 값으로 삼는다. 문제 번호 등 다른 숫자
    span과 섞이지 않도록 폰트를 엄격히 제한한다."""
    best_label = None
    best_dist = None
    for s in spans_cache:
        if s['font'] != 'DINPro-Medium' or s['text'].strip() != 'Level':
            continue
        dist = abs(s['bbox'][1] - marker['y0'])
        if dist < 40 and (best_dist is None or dist < best_dist):
            best_dist = dist
            best_label = s
    if best_label is None:
        return None
    label_y0, label_x1 = best_label['bbox'][1], best_label['bbox'][2]
    for s in spans_cache:
        if s['font'] != 'DINPro-Bold':
            continue
        if abs(s['bbox'][1] - label_y0) < 3 and -3 <= s['bbox'][0] - label_x1 < 15:
            text = s['text'].strip()
            if text.isdigit():
                return text
    return None


def extract_problems(pdf_path: str, out_dir: str, page_range: range | None = None) -> list[SumProblem]:
    doc = fitz.open(pdf_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    results: list[SumProblem] = []
    current_sub_no = 0  # 0이면 아직 소단원 도입부 전
    type_seq = 0

    for pno in (page_range if page_range is not None else range(doc.page_count)):
        page = doc[pno]

        sub_no = _detect_subsection_start(page)
        if sub_no and 1 <= sub_no <= len(SUBSECTION_ORDER):
            current_sub_no = sub_no
            type_seq = 0
            continue  # 도입부 페이지 자체에는 문제가 없다

        if current_sub_no == 0:
            continue

        markers = _find_problem_markers(page)
        if not markers:
            continue

        type_start_ys = _find_type_starts(page)
        spans_cache = list(_iter_spans(page))
        page_width, page_height = page.rect.width, page.rect.height

        for mk in markers:
            if any(abs(mk['y0'] - ty) < 30 for ty in type_start_ys):
                type_seq += 1

            same_col = [m for m in markers if m['column'] == mk['column']]
            same_col.sort(key=lambda m: m['y0'])
            i = same_col.index(mk)
            y1 = same_col[i + 1]['y0'] if i + 1 < len(same_col) else page_height

            x0 = 0 if mk['column'] == 0 else page_width / 2
            x1 = page_width / 2 if mk['column'] == 0 else page_width
            clip = fitz.Rect(x0, mk['y0'] - 5, x1, y1)

            pix = page.get_pixmap(dpi=200, clip=clip)
            img_name = f'{Path(pdf_path).stem}_{pno:04d}_{mk["number"]}.png'
            img_path = str(Path(out_dir) / img_name)
            pix.save(img_path)

            level = _find_level_near(page, mk, spans_cache)
            section_name, subsection_name = SUBSECTION_ORDER[current_sub_no - 1]

            results.append(SumProblem(
                number=mk['number'],
                section_name=section_name,
                subsection_name=subsection_name,
                type_seq=max(type_seq, 1),
                level=level,
                page_index=pno,
                image_path=img_path,
                text=page.get_text(clip=clip),
            ))

    doc.close()
    return results


if __name__ == '__main__':
    import sys
    from collections import Counter

    pdf_path = sys.argv[1]
    out_dir = sys.argv[2]
    problems = extract_problems(pdf_path, out_dir)
    print('총 문제 수:', len(problems))
    print('소단원별:', dict(Counter(p.subsection_name for p in problems)))
    print('Level별:', dict(Counter(p.level for p in problems)))
