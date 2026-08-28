"""
쎈수학 기하 "문제.pdf"에서 유형별로 문제를 잘라낸다.

미적분1과 완전히 같은 색상 마커·크기 임계값, 같은 TOC-OCR+제목 재동기화
방식이 그대로 통한다(직접 대조 확인함 - 같은 "쎈수학"/"신사고" 시리즈라서
유형/대표문제 알약 색상이 같다). 그래서 pdf_mi1_sen_extract.py의 마커
탐지·추출 로직을 그대로 재사용하고, 이 파일은 기하 전용 상수(소단원
순서, 목차 페이지 번호)만 갖는다.
"""
from __future__ import annotations

from pdf_mi1_sen_extract import Mi1Problem, extract_problems  # noqa: F401 (재노출)

GEO_SUBSECTION_ORDER = [
    ('이차곡선', '이차곡선'),
    ('이차곡선', '이차곡선의 접선'),
    ('공간도형과 공간좌표', '공간도형'),
    ('공간도형과 공간좌표', '공간좌표'),
    ('벡터', '벡터의 연산'),
    ('벡터', '벡터의 성분과 내적'),
    ('벡터', '도형의 방정식'),
]

TOC_PAGE_INDICES = [12, 52, 92]


if __name__ == '__main__':
    import sys
    from collections import Counter

    from pdf_mi1_toc_parse import parse_toc_pages

    pdf_path = sys.argv[1]
    out_dir = sys.argv[2]

    toc = parse_toc_pages(pdf_path, TOC_PAGE_INDICES, [name for _, name in GEO_SUBSECTION_ORDER])
    problems, warnings = extract_problems(pdf_path, out_dir, GEO_SUBSECTION_ORDER, toc)
    with open('geo_sen_extract_log.txt', 'w', encoding='utf-8') as f:
        f.write(f'총 문제 수: {len(problems)}\n')
        f.write(f'대표문제 수: {sum(1 for p in problems if p.is_daepyo)}\n')
        by_sub = Counter(p.subsection_name for p in problems)
        f.write(f'소단원별: {dict(by_sub)}\n')
        f.write(f'경고 {len(warnings)}건:\n')
        for w in warnings:
            f.write(f'  {w}\n')
    print('done, see geo_sen_extract_log.txt')
