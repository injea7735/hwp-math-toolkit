"""이미 가져온 NGD 문제(ngd_problem_id 있는 행)에 explanation을 채운다.

import_from_ngd.py는 이미 들어온 문제(ngd_problem_id로 식별)는 새로 안
건드리는 idempotent-insert-only 방식이라, explanation 필드를 나중에
추가한 지금은 기존 1,357개 행에 이 필드가 비어 있다. 원본 exam.db(읽기
전용)에서 같은 problems.id로 직접 재조회해서 채운다 - 가장 신뢰도 높은
소스(원본 그 자체)에서 다시 읽는 것이라 추측이 아니다.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy.orm import Session

from import_from_ngd import DEFAULT_NGD_DB, _fix_latex
from models import Problem, init_db


def backfill(session: Session, ngd_db_path: Path, apply: bool) -> dict:
    ngd_conn = sqlite3.connect(f"file:{ngd_db_path}?mode=ro", uri=True)
    ngd_conn.row_factory = sqlite3.Row
    explanations = {
        row["id"]: row["explanation"]
        for row in ngd_conn.execute("SELECT id, explanation FROM problems")
    }
    ngd_conn.close()

    rows = session.query(Problem).filter(Problem.ngd_problem_id.isnot(None)).all()
    stats = {"total": len(rows), "filled": 0, "no_source_text": 0, "already_had": 0}

    for row in rows:
        if row.explanation is not None:
            stats["already_had"] += 1
            continue
        raw = explanations.get(row.ngd_problem_id)
        fixed = _fix_latex(raw)
        if not fixed:
            stats["no_source_text"] += 1
            continue
        stats["filled"] += 1
        if apply:
            row.explanation = fixed

    if apply:
        session.commit()
    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--ngd-db", type=Path, default=DEFAULT_NGD_DB)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    engine = init_db()
    with Session(engine) as session:
        result = backfill(session, args.ngd_db, args.apply)
    mode = "적용됨" if args.apply else "드라이런(DB 미변경)"
    print(f"[{mode}] {result}")


if __name__ == "__main__":
    main()
