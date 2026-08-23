"""
pdf_sen_extract.extract_problems()로 뽑은 쎈수학 문제를 models.Problem에 넣는다.

ProblemType은 이미 import_sen_daepyo_types.py가 real 유형명으로 만들어
뒀으므로(code=f'{subject}-쎈-{subsection_name}-유형{type_no}') 그걸 그대로
찾아서 쓴다 - 없으면(예: taxonomy 시딩을 안 돌린 새 소단원) 이 자리에서
만든다.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from pdf_sen_extract import SenProblem
from import_workbook_outline import get_or_create_section, get_or_create_subsection
from models import Chapter, Problem, ProblemType, Source, init_db


def _get_or_create_source(session: Session, subject: str, pdf_path: str) -> Source:
    exam_name = f'{subject} 쎈수학 유형서(PDF)'
    src = session.query(Source).filter_by(exam_name=exam_name).one_or_none()
    if src is None:
        src = Source(exam_name=exam_name, material_kind='N제')
        session.add(src)
        session.flush()
    return src


def insert_problems(session: Session, subject: str, problems: list[SenProblem], pdf_path: str | None = None) -> int:
    chapter = session.query(Chapter).filter_by(name=subject).one()
    source = _get_or_create_source(session, subject, pdf_path or '')

    type_cache: dict[str, ProblemType] = {}
    created = 0

    for p in problems:
        code = f'{subject}-쎈-{p.subsection_name}-유형{p.type_no}'
        ptype = type_cache.get(code)
        if ptype is None:
            ptype = session.query(ProblemType).filter_by(code=code).one_or_none()
            if ptype is None:
                # taxonomy가 아직 안 심어져 있으면(예: 새 소단원) 이 자리에서 만든다.
                section = get_or_create_section(session, chapter, p.section_name)
                subsection = get_or_create_subsection(session, section, p.subsection_name)
                ptype = ProblemType(
                    subsection_id=subsection.id, code=code,
                    name=p.type_title, order=int(p.type_no),
                )
                session.add(ptype)
                session.flush()
            type_cache[code] = ptype

        image_paths_json = json.dumps([p.image_path], ensure_ascii=False)
        exists = session.query(Problem).filter_by(image_paths=image_paths_json).one_or_none()
        if exists is not None:
            continue

        session.add(Problem(
            problem_type_id=ptype.id,
            source_id=source.id,
            stem_latex='(이미지 참고)',
            answer=p.answer,
            question_kind='객관식',
            image_paths=image_paths_json,
            original_file_path=pdf_path,
        ))
        created += 1

    return created


if __name__ == '__main__':
    import sys

    subject = sys.argv[1]
    pdf_path = sys.argv[2]
    hwp_dir = sys.argv[3]
    out_dir = sys.argv[4]

    from pdf_sen_extract import extract_problems, SUBJECT_SUBSECTION_ORDERS

    problems, warnings = extract_problems(pdf_path, hwp_dir, out_dir, SUBJECT_SUBSECTION_ORDERS[subject])
    print('추출된 문제 수:', len(problems), '경고:', len(warnings))

    engine = init_db()
    with Session(engine) as session:
        created = insert_problems(session, subject, problems, pdf_path)
        session.commit()
        print('DB에 새로 넣은 문제 수:', created)
