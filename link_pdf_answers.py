"""
pdf_answer_extract.extract_answers()로 뽑은 문제번호->정답 매핑을
이미 image_paths로 저장되어 있는 Problem 행에 채워 넣는다.

문제 번호는 import_pdf_problems.py가 이미지 파일명 끝에
"_<번호3자리>.png" 로 남겨 놓은 걸 다시 읽어서 안다(스키마에 번호를
저장하는 별도 필드가 없어서, 파일명이 곧 자연키 역할을 한다).
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from pdf_answer_extract import extract_answers
from models import Problem, init_db

_NUMBER_IN_FILENAME = re.compile(r'_(\d{3})\.png$')


def link_answers(session: Session, subject: str, haeseol_pdf_path: str) -> tuple[int, int]:
    """반환값: (답을 채운 행 수, 매칭 실패 행 수)"""
    answers = extract_answers(haeseol_pdf_path)

    rows = (
        session.query(Problem)
        .filter(Problem.original_file_path.like(f'%{subject}%'))
        .filter(Problem.image_paths.isnot(None))
        .all()
    )

    updated, missing = 0, 0
    for p in rows:
        paths = json.loads(p.image_paths)
        m = _NUMBER_IN_FILENAME.search(paths[0]) if paths else None
        if not m:
            missing += 1
            continue
        number = m.group(1)
        answer = answers.get(number)
        if answer is None:
            missing += 1
            continue
        p.answer = answer
        updated += 1

    return updated, missing


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print('usage: link_pdf_answers.py <subject> <해설pdf경로>')
        raise SystemExit(1)

    subject, haeseol_path = sys.argv[1], sys.argv[2]
    engine = init_db()
    with Session(engine) as session:
        updated, missing = link_answers(session, subject, haeseol_path)
        session.commit()
        print('정답 채운 행 수:', updated, '/ 매칭 실패:', missing)
