"""
pdf_sumaessing_extract.extract_problems()로 뽑은 문제를 models.Problem에 넣는다.

이 자료는 소단원(SubSection)까지는 실제 이름으로 확인됐고, 유형(ProblemType)은
이름 없이 "대표문제" 등장 순서로만 구분되므로 소단원 안에서 "유형 N"이라는
순번 이름으로 만든다. 실제 유형명이 아니라는 걸 code/name에 남겨 둔다.
난이도는 Level 1~4를 DifficultyTier로 매핑한다(못 찾으면 None).
정답은 아직 안 넣는다 - 별도 해설 PDF 연결은 다음 단계.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from pdf_sumaessing_extract import SumProblem
from import_workbook_outline import get_or_create_section, get_or_create_subsection
from models import Chapter, DifficultyTier, Problem, ProblemType, Source, init_db

SUBJECT = '미적분2'


def _get_or_create_type(session: Session, subsection_id: int, section_name: str,
                         subsection_name: str, type_seq: int) -> ProblemType:
    code = f'{SUBJECT}-{subsection_name}-유형{type_seq}'
    ptype = session.query(ProblemType).filter_by(code=code).one_or_none()
    if ptype is None:
        ptype = ProblemType(
            subsection_id=subsection_id, code=code,
            name=f'유형 {type_seq}', order=type_seq,
        )
        session.add(ptype)
        session.flush()
    return ptype


def _get_or_create_tier(session: Session, level: str | None) -> DifficultyTier | None:
    if not level:
        return None
    name = f'Level {level}'
    tier = session.query(DifficultyTier).filter_by(name=name).one_or_none()
    if tier is None:
        tier = DifficultyTier(name=name, order=int(level) if level.isdigit() else 0)
        session.add(tier)
        session.flush()
    return tier


def _get_or_create_source(session: Session, pdf_path: str) -> Source:
    exam_name = f'{SUBJECT} 수매씽 유형서(PDF)'
    src = session.query(Source).filter_by(exam_name=exam_name).one_or_none()
    if src is None:
        src = Source(exam_name=exam_name, material_kind='N제')
        session.add(src)
        session.flush()
    return src


def insert_problems(session: Session, parsed: list[SumProblem], pdf_path: str | None = None) -> int:
    chapter = session.query(Chapter).filter_by(name=SUBJECT).one()
    source = _get_or_create_source(session, pdf_path or '')

    subsection_cache: dict[str, int] = {}
    created = 0

    for p in parsed:
        key = f'{p.section_name}::{p.subsection_name}'
        if key not in subsection_cache:
            section = get_or_create_section(session, chapter, p.section_name)
            subsection = get_or_create_subsection(session, section, p.subsection_name)
            subsection_cache[key] = subsection.id
        subsection_id = subsection_cache[key]

        ptype = _get_or_create_type(session, subsection_id, p.section_name, p.subsection_name, p.type_seq)
        tier = _get_or_create_tier(session, p.level)

        exists = (
            session.query(Problem)
            .filter_by(image_paths=json.dumps([p.image_path], ensure_ascii=False))
            .one_or_none()
        )
        if exists is not None:
            continue

        session.add(Problem(
            problem_type_id=ptype.id,
            difficulty_tier_id=tier.id if tier else None,
            source_id=source.id,
            stem_latex=p.text.strip() or '(텍스트 추출 실패 - 이미지 참고)',
            question_kind='객관식',
            image_paths=json.dumps([p.image_path], ensure_ascii=False),
            original_file_path=pdf_path,
        ))
        created += 1

    return created


if __name__ == '__main__':
    import sys
    from pdf_sumaessing_extract import extract_problems

    pdf_path = sys.argv[1]
    out_dir = sys.argv[2]

    parsed = extract_problems(pdf_path, out_dir)
    print('추출된 문제 수:', len(parsed))

    engine = init_db()
    with Session(engine) as session:
        created = insert_problems(session, parsed, pdf_path)
        session.commit()
        print('DB에 새로 넣은 문제 수:', created)
