"""쎈수학 문제 이미지에서 하/중/상 난이도 배지와 서술형 배지를 읽어
Problem.difficulty_label / Problem.question_kind를 채운다.

extract_sen_difficulty_badges.detect_badges()가 실제 신호(색+모양)를 못
찾으면 None을 반환하고, 이 스크립트는 그 경우 difficulty_label을 절대
건드리지 않는다(대표문제이거나 크롭이 어긋난 경우 - 추측해서 채우지 않는다).
question_kind는 항상 갱신한다(배지가 없으면 기존 파이프라인 기본값과 같은
'객관식'이라 값이 바뀌지 않음).

사용: python backfill_sen_difficulty.py 기하 [--apply]
--apply 없이 실행하면 통계만 보여주고 DB는 건드리지 않는다.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

from sqlalchemy.orm import Session

from extract_sen_difficulty_badges import detect_badges
from models import Chapter, Problem, ProblemType, Section, SubSection, init_db


def backfill(session: Session, chapter_name: str, apply: bool) -> dict:
    rows = (
        session.query(Problem)
        .select_from(Problem)
        .join(ProblemType, Problem.problem_type_id == ProblemType.id)
        .join(SubSection, ProblemType.subsection_id == SubSection.id)
        .join(Section, SubSection.section_id == Section.id)
        .join(Chapter, Section.chapter_id == Chapter.id)
        .filter(Chapter.name == chapter_name)
        .filter(Problem.image_paths.isnot(None))
        .all()
    )
    difficulty_counter = Counter()
    kind_counter = Counter()
    changed = 0
    for p in rows:
        path = json.loads(p.image_paths)[0]
        difficulty, kind = detect_badges(path)
        difficulty_counter[difficulty] += 1
        kind_counter[kind] += 1
        if apply:
            touched = False
            if difficulty is not None and p.difficulty_label != difficulty:
                p.difficulty_label = difficulty
                touched = True
            if p.question_kind != kind:
                p.question_kind = kind
                touched = True
            if touched:
                changed += 1
    if apply:
        session.commit()
    return {
        'total': len(rows),
        'difficulty_dist': dict(difficulty_counter),
        'kind_dist': dict(kind_counter),
        'rows_changed': changed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('chapter')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    engine = init_db()
    with Session(engine) as session:
        result = backfill(session, args.chapter, args.apply)
    mode = '적용됨' if args.apply else '드라이런(DB 미변경)'
    print(f'[{mode}] {args.chapter}: {result}')


if __name__ == '__main__':
    main()
