import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_geo_sen_extract import GEO_SUBSECTION_ORDER, TOC_PAGE_INDICES, extract_problems


def test_subsection_order_covers_all_three_sections():
    section_names = {section for section, _ in GEO_SUBSECTION_ORDER}
    assert section_names == {'이차곡선', '공간도형과 공간좌표', '벡터'}


def test_subsection_order_has_no_duplicate_subsections():
    subsection_names = [name for _, name in GEO_SUBSECTION_ORDER]
    assert len(subsection_names) == len(set(subsection_names))


def test_toc_page_indices_matches_number_of_대단원():
    # 목차 페이지는 대단원(이차곡선/공간도형과 공간좌표/벡터)마다 하나씩,
    # 소단원 개수(7개)와는 다르다.
    assert len(TOC_PAGE_INDICES) == 3


def test_extract_problems_reexported_from_mi1_module():
    # pdf_geo_sen_extract.py는 마커 탐지 로직을 새로 안 만들고
    # pdf_mi1_sen_extract.extract_problems()를 그대로 재사용한다 - 같은
    # 함수 객체인지 확인해서 실수로 복제되지 않았음을 보장한다.
    from pdf_mi1_sen_extract import extract_problems as mi1_extract_problems
    assert extract_problems is mi1_extract_problems
