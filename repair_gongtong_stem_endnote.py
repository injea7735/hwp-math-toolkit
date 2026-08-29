"""hwp_workbook_parse.extract_problems()의 EndNote 버그(2026-08-29 발견,
같은 파일의 docstring 참고) 때문에 stem_latex 앞에 정답 각주의 풀이가
그대로 붙어 저장된 기존 공통수학1/2 행을 원본 재추출로 복구한다.

버그 자체는 코드에서 이미 고쳐졌으므로, 여기서는 고쳐진 추출기로 다시
뽑은 "진짜" stem/choices를 기존 행에 맞춰 넣는다. 매칭은 (problem_type_id,
answer) 만으로는 부족할 수 있어(같은 유형 안에 같은 정답 기호가 여러 번
나올 수 있음), 오염된 stem이 "쓰레기 접두사 + 진짜 stem" 형태라는 사실을
이용한다 - 기존 stem_latex가 새로 뽑은 올바른 body로 정확히 끝나는(suffix)
행을 찾는다. 이미 깨끗한 행(stem_latex == body)은 건드리지 않는다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from hwp_workbook_parse import extract_outline, extract_problems
from import_workbook_problems import split_choices
from models import Problem, ProblemType, init_db
from backfill_gongtong_difficulty import FILES

import json


def repair(session: Session, apply: bool) -> dict:
    stats = {
        "already_clean": 0,
        "fixed": 0,
        "no_type": 0,
        "no_match": 0,
        "ambiguous": 0,
    }
    type_cache: dict[str, ProblemType | None] = {}
    examples: list[tuple[int, str, str]] = []

    for subject, path, unit_title_override in FILES:
        outline = extract_outline(path)
        unit_title = unit_title_override or outline.unit_title
        if not unit_title:
            continue

        for p in extract_problems(path):
            code = f'{subject}-{unit_title}-{p.type_no}'
            if code not in type_cache:
                type_cache[code] = session.query(ProblemType).filter_by(code=code).one_or_none()
            ptype = type_cache[code]
            if ptype is None:
                stats["no_type"] += 1
                continue

            body, choices = split_choices(p.stem)

            exact = (
                session.query(Problem)
                .filter_by(problem_type_id=ptype.id, stem_latex=body)
                .all()
            )
            if exact:
                stats["already_clean"] += 1
                continue

            candidates = (
                session.query(Problem)
                .filter_by(problem_type_id=ptype.id)
                .filter(Problem.stem_latex.like(f'%{body[-40:]}'))
                .all()
            )
            candidates = [c for c in candidates if c.stem_latex.endswith(body) and c.stem_latex != body]

            if len(candidates) == 0:
                stats["no_match"] += 1
                continue
            if len(candidates) > 1:
                stats["ambiguous"] += 1
                continue

            row = candidates[0]
            stats["fixed"] += 1
            if len(examples) < 3:
                examples.append((row.id, row.stem_latex[:60], body[:60]))
            if apply:
                row.stem_latex = body
                row.choices_latex = json.dumps(choices, ensure_ascii=False) if choices else None

    if apply:
        session.commit()
    stats["examples"] = examples
    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    engine = init_db()
    with Session(engine) as session:
        result = repair(session, args.apply)
    mode = '적용됨' if args.apply else '드라이런(DB 미변경)'
    print(f'[{mode}] {result}')


if __name__ == '__main__':
    main()
