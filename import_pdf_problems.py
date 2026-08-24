"""
pdf_problem_extract.extract_problems()로 잘라낸 문제 이미지를 models.Problem
테이블에 넣는다.

이 PDF들은 수식이 커스텀 폰트 글리프라 텍스트로 못 뽑으므로(pdf_problem_extract.py
docstring 참고), 문제 본문은 이미지 그대로 저장하고(image_paths), 추출되는
텍스트는 검색/참고용으로만 stem_latex에 같이 넣는다(수식 부분은 깨져 있을 수
있음 - 알고 씀). 유형(ProblemType)은 이 자료에 없으므로 대단원(Section)마다
"미분류" 자리표시자 유형 하나만 만들어 연결하고, 실제 분류축은
difficulty_tier(핵심/심화/최고난도 유형)를 쓴다. 정답은 별도 "해설" PDF에
있어서 아직 연결하지 않았다(answer=None).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from pdf_problem_extract import ExtractedProblem, extract_problems
from import_workbook_outline import get_or_create_section, get_or_create_subsection
from import_workbook_problems import guess_question_kind
from models import Chapter, DifficultyTier, Problem, ProblemType, Source, init_db

PLACEHOLDER_SUBSECTION = '전체'
PLACEHOLDER_TYPE_NAME = '미분류(난이도만 구분)'


def _get_or_create_placeholder_type(session: Session, subject: str, section_name: str) -> ProblemType:
    chapter = session.query(Chapter).filter_by(name=subject).one()
    section = get_or_create_section(session, chapter, section_name)
    subsection = get_or_create_subsection(session, section, PLACEHOLDER_SUBSECTION)

    code = f'{subject}-{section_name}-미분류'
    ptype = session.query(ProblemType).filter_by(code=code).one_or_none()
    if ptype is None:
        ptype = ProblemType(subsection_id=subsection.id, code=code, name=PLACEHOLDER_TYPE_NAME)
        session.add(ptype)
        session.flush()
    return ptype


def _get_or_create_source(session: Session, subject: str, pdf_path: str) -> Source:
    exam_name = f'{subject} 내신고쟁이 유형서(PDF)'
    src = session.query(Source).filter_by(exam_name=exam_name).one_or_none()
    if src is None:
        src = Source(exam_name=exam_name, material_kind='N제')
        session.add(src)
        session.flush()
    return src


def insert_pdf_problems(
    session: Session, subject: str, section_names: list[str], parsed: list[ExtractedProblem],
    pdf_path: str,
) -> int:
    source = _get_or_create_source(session, subject, pdf_path)
    type_cache: dict[int, ProblemType] = {}
    tier_cache: dict[str, DifficultyTier | None] = {}

    created = 0
    for p in parsed:
        if p.section_index not in type_cache:
            section_name = section_names[p.section_index]
            type_cache[p.section_index] = _get_or_create_placeholder_type(session, subject, section_name)
        ptype = type_cache[p.section_index]

        if p.tier_name not in tier_cache:
            tier_cache[p.tier_name] = (
                session.query(DifficultyTier).filter_by(name=p.tier_name).one_or_none()
                if p.tier_name else None
            )
        tier = tier_cache[p.tier_name]

        exists = (
            session.query(Problem)
            .filter_by(problem_type_id=ptype.id, image_paths=json.dumps([p.image_path], ensure_ascii=False))
            .one_or_none()
        )
        if exists is not None:
            continue

        session.add(Problem(
            problem_type_id=ptype.id,
            difficulty_tier_id=tier.id if tier else None,
            source_id=source.id,
            stem_latex=p.text or '(텍스트 추출 실패 - 이미지 참고)',
            question_kind=guess_question_kind(p.text or ''),
            image_paths=json.dumps([p.image_path], ensure_ascii=False),
            original_file_path=pdf_path,
        ))
        created += 1

    return created


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 5:
        print('usage: import_pdf_problems.py <subject> <pdf경로> <이미지저장폴더> <대단원이름,콤마구분>')
        raise SystemExit(1)

    subject, pdf_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    section_names = sys.argv[4].split(',')

    parsed = extract_problems(pdf_path, out_dir, section_count=len(section_names))
    print('추출된 문제 수:', len(parsed))

    engine = init_db()
    with Session(engine) as session:
        created = insert_pdf_problems(session, subject, section_names, parsed, pdf_path)
        session.commit()
        print('DB에 새로 넣은 문제 수:', created)
