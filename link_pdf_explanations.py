"""pdf_answer_extract.extract_explanations()로 뽑은 문제번호->풀이 매핑을
이미 image_paths로 저장되어 있는 Problem 행에 채워 넣는다.

문제 번호 매칭 방식은 link_pdf_answers.py와 동일 - 이미지 파일명 끝의
"_<번호3자리>.png"를 자연키로 쓴다.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from pdf_answer_extract import extract_explanations
from models import Problem, init_db

_NUMBER_IN_FILENAME = re.compile(r'_(\d{3})\.png$')


def link_explanations(session: Session, subject: str, haeseol_pdf_path: str) -> tuple[int, int]:
    """반환값: (해설을 채운 행 수, 매칭 실패 행 수)"""
    explanations = extract_explanations(haeseol_pdf_path)

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
        explanation = explanations.get(number)
        if explanation is None:
            missing += 1
            continue
        p.explanation = explanation
        updated += 1

    return updated, missing


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print('usage: link_pdf_explanations.py <subject> <해설pdf경로>')
        raise SystemExit(1)

    subject, haeseol_path = sys.argv[1], sys.argv[2]
    engine = init_db()
    with Session(engine) as session:
        updated, missing = link_explanations(session, subject, haeseol_path)
        session.commit()
        print('해설 채운 행 수:', updated, '/ 매칭 실패:', missing)
