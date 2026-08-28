"""
쎈수학 기하(22개정) 실제 유형 taxonomy를 반영한다. import_mi1_sen_types.py와
같은 흐름(대표문제 HWP 인덱스가 없어 TOC-OCR 기반) - 기하는 이전에 아무
데이터도 없던 새 Chapter라 stale 데이터 정리가 필요 없다는 점만 다르다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from import_workbook_outline import (
    get_or_create_chapter, get_or_create_section, get_or_create_subsection,
)
from models import ProblemType, init_db

SUBJECT = '기하'


def insert_types(
    session: Session, subsection_order: list[tuple[str, str]],
    toc: dict[str, list[tuple[str, str]]],
) -> int:
    chapter = get_or_create_chapter(session, SUBJECT)
    created = 0
    for section_name, subsection_name in subsection_order:
        section = get_or_create_section(session, chapter, section_name)
        subsection = get_or_create_subsection(session, section, subsection_name)
        for type_no, title in toc[subsection_name]:
            code = f'{SUBJECT}-쎈-{subsection_name}-유형{type_no}'
            ptype = session.query(ProblemType).filter_by(code=code).one_or_none()
            if ptype is None:
                ptype = ProblemType(
                    subsection_id=subsection.id, code=code,
                    name=title, order=int(type_no),
                )
                session.add(ptype)
                session.flush()
                created += 1
    return created


if __name__ == '__main__':
    import sys

    from pdf_geo_sen_extract import GEO_SUBSECTION_ORDER, TOC_PAGE_INDICES
    from pdf_mi1_toc_parse import parse_toc_pages

    pdf_path = sys.argv[1]

    toc = parse_toc_pages(pdf_path, TOC_PAGE_INDICES, [name for _, name in GEO_SUBSECTION_ORDER])

    engine = init_db()
    with Session(engine) as session:
        created = insert_types(session, GEO_SUBSECTION_ORDER, toc)
        session.commit()
        print(f'새로 만든 ProblemType: {created}')
