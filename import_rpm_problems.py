"""
pdf_rpm_extract.extract_subsections()로 뽑은 소단원별 문제 페이지 묶음을
models.Problem에 넣는다.

개별 문제/유형 단위로 못 쪼갰으므로(pdf_rpm_extract.py 참고) 소단원 하나 =
Problem 하나로 저장한다. image_paths에 그 소단원의 문제 페이지 이미지들이
전부 들어간다. ProblemType은 소단원마다 자리표시자 하나("전체")만 만든다.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from pdf_rpm_extract import RpmSubsectionGroup
from import_workbook_outline import get_or_create_section, get_or_create_subsection
from models import Chapter, Problem, ProblemType, Source, init_db

SUBJECT = '미적분2'
PLACEHOLDER_TYPE_NAME = '전체(소단원 단위로만 구분)'


def _get_or_create_source(session: Session, pdf_path: str) -> Source:
    exam_name = f'{SUBJECT} 개념원리 RPM 유형서(PDF)'
    src = session.query(Source).filter_by(exam_name=exam_name).one_or_none()
    if src is None:
        src = Source(exam_name=exam_name, material_kind='N제')
        session.add(src)
        session.flush()
    return src


def insert_subsections(session: Session, groups: list[RpmSubsectionGroup], pdf_path: str | None = None) -> int:
    chapter = session.query(Chapter).filter_by(name=SUBJECT).one()
    source = _get_or_create_source(session, pdf_path or '')

    created = 0
    for g in groups:
        section = get_or_create_section(session, chapter, g.section_name)
        subsection = get_or_create_subsection(session, section, g.subsection_name)

        code = f'{SUBJECT}-{g.subsection_name}-전체'
        ptype = session.query(ProblemType).filter_by(code=code).one_or_none()
        if ptype is None:
            ptype = ProblemType(subsection_id=subsection.id, code=code, name=PLACEHOLDER_TYPE_NAME)
            session.add(ptype)
            session.flush()

        image_paths_json = json.dumps(g.image_paths, ensure_ascii=False)
        exists = session.query(Problem).filter_by(image_paths=image_paths_json).one_or_none()
        if exists is not None:
            continue

        session.add(Problem(
            problem_type_id=ptype.id,
            source_id=source.id,
            stem_latex='\n'.join(t.strip() for t in g.text_parts if t.strip()) or '(이미지 참고)',
            question_kind='객관식',
            image_paths=image_paths_json,
            original_file_path=pdf_path,
        ))
        created += 1

    return created


if __name__ == '__main__':
    import sys
    from pdf_rpm_extract import extract_subsections

    pdf_path = sys.argv[1]
    out_dir = sys.argv[2]

    groups = extract_subsections(pdf_path, out_dir)
    print('추출된 소단원 수:', len(groups))

    engine = init_db()
    with Session(engine) as session:
        created = insert_subsections(session, groups, pdf_path)
        session.commit()
        print('DB에 새로 넣은 소단원 수:', created)
