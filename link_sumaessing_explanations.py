"""sumaessing_answer_extract.extract_explanations()로 뽑은 풀이를 이미
저장되어 있는 수매씽 Problem 행에 채워 넣는다. 번호는 이미지 파일명 끝의
"_<번호4자리>.png"에서 읽는다 (link_sumaessing_answers.py와 동일한 매칭).
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from sumaessing_answer_extract import extract_explanations
from models import Problem, init_db

_NUMBER_IN_FILENAME = re.compile(r'_(\d{4})\.png$')


def link_explanations(session: Session, haeseol_pdf_path: str) -> tuple[int, int]:
    explanations = extract_explanations(haeseol_pdf_path)

    rows = (
        session.query(Problem)
        .filter(Problem.original_file_path.like('%수매씽%'))
        .all()
    )

    updated, missing = 0, 0
    for p in rows:
        paths = json.loads(p.image_paths)
        m = _NUMBER_IN_FILENAME.search(paths[0]) if paths else None
        if not m:
            missing += 1
            continue
        explanation = explanations.get(m.group(1))
        if explanation is None:
            missing += 1
            continue
        p.explanation = explanation
        updated += 1

    return updated, missing


if __name__ == '__main__':
    import sys

    haeseol_path = sys.argv[1]
    engine = init_db()
    with Session(engine) as session:
        updated, missing = link_explanations(session, haeseol_path)
        session.commit()
        print('해설 채운 행 수:', updated, '/ 매칭 실패:', missing)
