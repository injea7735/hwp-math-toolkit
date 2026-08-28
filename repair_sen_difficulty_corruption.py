"""backfill_sen_difficulty.py를 4과목(대수/미적분1/미적분2/확률과 통계)
전체에 돌렸다가, 쎈수학이 아닌 다른 출처(내신고쟁이 PDF/수매씽/RPM/NGD)
문제 이미지에서 배지 검출기가 오탐(false positive)을 일으켜
difficulty_label/question_kind를 잘못 덮어쓴 걸 발견하고 되돌리는 1회성
복구 스크립트.

각 출처별로 원래 값을 "추측"이 아니라 실제 원본 로직/원본 데이터에서
그대로 다시 계산해서 복원한다:
- NGD 출처(ngd_problem_id 있음): 원본 exam.db에서 difficulty/qtype을 직접
  다시 읽어온다(가장 신뢰도 높음 - 실제 원본 소스).
- 내신고쟁이 PDF 출처(원본 파일명에 "유형내신" 포함): difficulty_label은
  원래 전부 None이었음(사전 확인됨) -> None으로 복원. question_kind는
  import_pdf_problems.py가 실제로 썼던 것과 동일한 함수
  (import_workbook_problems.guess_question_kind)를 저장된 stem_latex에
  다시 돌려서 복원.
- 수매씽/RPM 출처: 두 임포터 모두 difficulty_label을 전혀 안 쓰고
  question_kind는 항상 '객관식'으로 고정 -> difficulty_label=None,
  question_kind='객관식'으로 복원.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy.orm import Session

from import_workbook_problems import guess_question_kind
from models import Chapter, Problem, ProblemType, Section, SubSection, init_db

NGD_DB = Path.home() / "AppData" / "Local" / "examtool" / "exam.db"
AFFECTED_CHAPTERS = ["대수", "미적분1", "미적분2", "확률과 통계"]


def _load_ngd_lookup() -> dict[int, tuple[str | None, str | None]]:
    con = sqlite3.connect(f"file:{NGD_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id, difficulty, qtype FROM problems").fetchall()
    con.close()
    return {r["id"]: (r["difficulty"], r["qtype"]) for r in rows}


def repair(session: Session, apply: bool) -> dict:
    ngd_lookup = _load_ngd_lookup()
    rows = (
        session.query(Problem)
        .select_from(Problem)
        .join(ProblemType, Problem.problem_type_id == ProblemType.id)
        .join(SubSection, ProblemType.subsection_id == SubSection.id)
        .join(Section, SubSection.section_id == Section.id)
        .join(Chapter, Section.chapter_id == Chapter.id)
        .filter(Chapter.name.in_(AFFECTED_CHAPTERS))
        .filter(Problem.image_paths.isnot(None))
        .filter(~Problem.image_paths.like('%쎈수학%'))
        .all()
    )

    stats = {"ngd": 0, "old_pdf": 0, "sumaessing_or_rpm": 0, "unmatched": 0, "changed": 0}
    unmatched_examples = []
    for p in rows:
        ofp = p.original_file_path or ''
        if p.ngd_problem_id is not None:
            stats["ngd"] += 1
            difficulty, qtype = ngd_lookup.get(p.ngd_problem_id, (None, None))
            new_label = difficulty
            new_kind = qtype or "객관식"
        elif '유형내신' in ofp:
            stats["old_pdf"] += 1
            new_label = None
            new_kind = guess_question_kind(p.stem_latex or '')
        elif '수매씽' in ofp or 'RPM' in ofp:
            stats["sumaessing_or_rpm"] += 1
            new_label = None
            new_kind = "객관식"
        else:
            stats["unmatched"] += 1
            if len(unmatched_examples) < 10:
                unmatched_examples.append((p.id, ofp, p.ngd_problem_id))
            continue

        if p.difficulty_label != new_label or p.question_kind != new_kind:
            stats["changed"] += 1
            if apply:
                p.difficulty_label = new_label
                p.question_kind = new_kind

    if apply:
        session.commit()
    stats["total_rows_considered"] = len(rows)
    stats["unmatched_examples"] = unmatched_examples
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
