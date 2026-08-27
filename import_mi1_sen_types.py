"""
쎈수학 미적분Ⅰ(22개정) 실제 유형 taxonomy를 반영한다.

미적분1은 다른 쎈수학 과목과 달리 "대표문제" HWP 인덱스가 없어서(대신
pdf_mi1_toc_parse.py가 대단원별 목차 페이지를 OCR해 유형 제목을 뽑는다),
import_sen_daepyo_types.py의 HWP 기반 흐름을 그대로 쓸 수 없다 - 이 모듈은
그 대체판이다.

2026-08-23에 "22개정 미적분Ⅰ용 쎈 유형서가 없다"는 잘못된 전제로 구교육과정
"수학Ⅱ" 쎈 대표문제 HWP를 대신 심어 둔 ProblemType 151개(코드에 '-쎈-' 포함)가
이미 있었다 - 연결된 Problem 행이 0개임을 확인했으므로(2026-08-24/25 세션)
안전하게 지우고 이 실제 22개정 자료로 교체한다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from import_workbook_outline import get_or_create_section, get_or_create_subsection
from models import Chapter, ProblemType, Section, SubSection, init_db

SUBJECT = '미적분1'


def delete_stale_sen_types(session: Session) -> int:
    """2026-08-23에 구교육과정 대체로 심어둔 미사용 '-쎈-' ProblemType을 지운다."""
    chapter = session.query(Chapter).filter_by(name=SUBJECT).one()
    stale = (
        session.query(ProblemType)
        .join(SubSection, ProblemType.subsection_id == SubSection.id)
        .join(Section, SubSection.section_id == Section.id)
        .filter(Section.chapter_id == chapter.id, ProblemType.code.contains('-쎈-'))
        .all()
    )
    for t in stale:
        session.delete(t)
    return len(stale)


def insert_types(
    session: Session, subsection_order: list[tuple[str, str]],
    toc: dict[str, list[tuple[str, str]]],
) -> int:
    chapter = session.query(Chapter).filter_by(name=SUBJECT).one()
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

    from pdf_mi1_sen_extract import MI1_SUBSECTION_ORDER, TOC_PAGE_INDICES
    from pdf_mi1_toc_parse import parse_toc_pages

    pdf_path = sys.argv[1]

    toc = parse_toc_pages(pdf_path, TOC_PAGE_INDICES, [name for _, name in MI1_SUBSECTION_ORDER])

    engine = init_db()
    with Session(engine) as session:
        deleted = delete_stale_sen_types(session)
        created = insert_types(session, MI1_SUBSECTION_ORDER, toc)
        session.commit()
        print(f'삭제된 stale ProblemType: {deleted}, 새로 만든 ProblemType: {created}')
