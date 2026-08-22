"""
hwp_workbook_parse.extract_outline()로 뽑은 단원/유형 구조를
models.py의 taxonomy(Chapter > Section > SubSection > ProblemType)에 저장한다.

파일 하나 = Section(중단원) 하나로 본다. 이 파서는 아직 소단원 단위로
더 쪼개진 데이터를 주지 않으므로, SubSection은 Section과 동명(1:1)으로
만들어 두는 자리표시자다 — 나중에 실제 소단원 구분이 생기면 그때 나눈다.
문제 본문은 아직 다루지 않으므로 ProblemType만 만들고 Problem은 만들지 않는다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from hwp_workbook_parse import extract_outline
from models import Chapter, Section, SubSection, ProblemType, init_db


def _get_or_create_chapter(session: Session, name: str) -> Chapter:
    chapter = session.query(Chapter).filter_by(name=name).one_or_none()
    if chapter is None:
        chapter = Chapter(name=name, order=len(session.query(Chapter).all()))
        session.add(chapter)
        session.flush()
    return chapter


def _get_or_create_section(session: Session, chapter: Chapter, name: str) -> Section:
    section = (
        session.query(Section)
        .filter_by(chapter_id=chapter.id, name=name)
        .one_or_none()
    )
    if section is None:
        section = Section(chapter_id=chapter.id, name=name, order=len(chapter.sections))
        session.add(section)
        session.flush()
    return section


def _get_or_create_subsection(session: Session, section: Section, name: str) -> SubSection:
    subsection = (
        session.query(SubSection)
        .filter_by(section_id=section.id, name=name)
        .one_or_none()
    )
    if subsection is None:
        subsection = SubSection(section_id=section.id, name=name, order=len(section.subsections))
        session.add(subsection)
        session.flush()
    return subsection


def import_outline_file(session: Session, subject: str, path: str, unit_title_override: str | None = None) -> int:
    """유형서 hwp 파일 하나를 taxonomy에 반영한다. 새로 만든 ProblemType 수를 반환."""
    outline = extract_outline(path)
    unit_title = unit_title_override or outline.unit_title
    if not unit_title:
        return 0

    chapter = _get_or_create_chapter(session, subject)
    section = _get_or_create_section(session, chapter, unit_title)
    subsection = _get_or_create_subsection(session, section, unit_title)

    created = 0
    for t in outline.types:
        code = f"{subject}-{unit_title}-{t.no}"
        existing = session.query(ProblemType).filter_by(code=code).one_or_none()
        if existing is None:
            session.add(ProblemType(
                subsection_id=subsection.id,
                code=code,
                name=t.title,
                order=int(t.no),
            ))
            created += 1
    return created


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print('usage: import_workbook_outline.py <subject> <hwp파일...>')
        raise SystemExit(1)

    subject = sys.argv[1]
    paths = sys.argv[2:]

    engine = init_db()
    with Session(engine) as session:
        total = 0
        for p in paths:
            n = import_outline_file(session, subject, p)
            print(f'{p}: +{n}')
            total += n
        session.commit()
        print('총 신규 유형:', total)
