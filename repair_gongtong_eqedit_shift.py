"""
2026-08-29에 찾은 방정식(EqEdit) 큐 밀림 버그 복구 스크립트.

hwp_workbook_parse.extract_problems()에 있던 버그로, 파일 맨 앞
(첫 AutoNumbering 이전)에 나온 수식 1개가 소비되지 않고 건너뛰어지면서
그 뒤로 이어지는 파일 전체의 수식이 한 칸씩 밀려 저장된 문제가 있었다.
영향받은 파일은 04복소수와이차방정식.hwp, 05이차방정식과이차함수.hwp 두 개뿐
(전체 스캔으로 확인 완료).

DB에는 문제별 seq(유형 내 순번)가 저장되어 있지 않으므로, 같은 유형 안에서
"삽입 순서(id 오름차순) == 원본 seq 순서"라는 가정으로 기존 행과 새로
고쳐서 추출한 문제를 1:1로 매칭해 stem_latex/choices_latex/answer를
덮어쓴다. 개수가 유형별로 정확히 일치하는지 먼저 검증한다.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from backfill_gongtong_difficulty import FILES as _ALL_FILES
from hwp_workbook_parse import extract_outline, extract_problems
from import_workbook_problems import split_choices, guess_question_kind
from models import init_db, Problem, ProblemType

_TARGET_NAMES = ('04복소수와이차방정식.hwp', '05이차방정식과이차함수.hwp')
FILES = [
    (subject, path)
    for subject, path, _override in _ALL_FILES
    if path.endswith(_TARGET_NAMES)
]


def repair(session: Session, apply: bool) -> None:
    for subject, path in FILES:
        outline = extract_outline(path)
        unit_title = outline.unit_title
        parsed = extract_problems(path)

        db_rows = (
            session.query(Problem)
            .filter(Problem.original_file_path == path)
            .order_by(Problem.id.asc())
            .all()
        )
        print(f'\n=== {path.split(chr(92))[-1]} (unit={unit_title}) ===')
        print(f'파싱된 문제 수: {len(parsed)} / DB 행 수: {len(db_rows)}')

        by_type_new: dict[str, list] = {}
        for p in parsed:
            by_type_new.setdefault(p.type_no, []).append(p)

        by_type_old: dict[str, list[Problem]] = {}
        type_cache: dict[str, ProblemType | None] = {}
        for row in db_rows:
            ptype = session.get(ProblemType, row.problem_type_id)
            by_type_old.setdefault(ptype.code.rsplit('-', 1)[-1], []).append(row)

        mismatch = False
        for type_no in sorted(set(by_type_new) | set(by_type_old)):
            n_new = len(by_type_new.get(type_no, []))
            n_old = len(by_type_old.get(type_no, []))
            if n_new != n_old:
                mismatch = True
                print(f'  !! 유형 {type_no}: 파싱 {n_new}개 vs DB {n_old}개 - 개수 불일치')
        if mismatch:
            print('  개수 불일치가 있어 이 파일은 건너뜁니다 (수동 확인 필요).')
            continue

        updated = 0
        for type_no in by_type_new:
            news = by_type_new[type_no]
            olds = by_type_old.get(type_no, [])
            for new_p, old_row in zip(news, olds):
                body, choices = split_choices(new_p.stem)
                new_choices_json = json.dumps(choices, ensure_ascii=False) if choices else None
                if old_row.stem_latex == body and old_row.choices_latex == new_choices_json:
                    continue
                if apply:
                    old_row.stem_latex = body
                    old_row.choices_latex = new_choices_json
                    old_row.answer = new_p.answer
                    old_row.question_kind = guess_question_kind(new_p.answer)
                updated += 1
        print(f'  변경 대상 행: {updated} / {len(db_rows)}')

    if apply:
        session.commit()
        print('\n적용 완료 (commit)')
    else:
        session.rollback()
        print('\ndry-run (--apply로 실제 반영)')


if __name__ == '__main__':
    import sys

    apply = '--apply' in sys.argv
    engine = init_db()
    with Session(engine) as session:
        repair(session, apply)
