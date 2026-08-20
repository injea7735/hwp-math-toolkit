"""NGD 문제은행(exam.db)에서 문제를 읽어와 models.py 스키마로 가져오는 임포터.

NGD는 exam.db(SQLite)에 problems/units/exams를 평평한 구조로 담고 있고, 수식은
이미 body/explanation 안에 LaTeX 비슷한 형태로 변환되어 있다 (`->`만 `\\to`로 바꿔주면 됨).
우리 스키마는 대단원>중단원>소단원>유형의 4단계 분류를 요구하지만 NGD의 unit은 평평한
1단계뿐이라, 각 unit을 "NGD 가져오기" 아래 소단원+유형 하나로 placeholder 매핑한다.
나중에 DB에서 직접 대/중단원으로 재배치하면 된다.

원본 exam.db는 읽기 전용으로만 연다 (NGD 앱이 그 DB를 실시간으로 쓰고 있으므로).
"""
from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path

from sqlalchemy.orm import Session

from models import Chapter, Section, SubSection, ProblemType, Source, Problem, init_db

DEFAULT_NGD_DB = Path.home() / "AppData" / "Local" / "examtool" / "exam.db"

PLACEHOLDER_CHAPTER = "NGD 가져오기"
FALLBACK_UNIT_NAME = "미분류"


def _fix_latex(text: str | None) -> str | None:
    if text is None:
        return None
    return text.replace("->", r"\to")


def _get_or_create_problem_type(session: Session, cache: dict[str, ProblemType], unit_name: str) -> ProblemType:
    if unit_name in cache:
        return cache[unit_name]

    chapter = session.query(Chapter).filter_by(name=PLACEHOLDER_CHAPTER).one_or_none()
    if chapter is None:
        chapter = Chapter(name=PLACEHOLDER_CHAPTER)
        session.add(chapter)

    section = session.query(Section).filter_by(name=PLACEHOLDER_CHAPTER, chapter=chapter).one_or_none()
    if section is None:
        section = Section(name=PLACEHOLDER_CHAPTER, chapter=chapter)
        session.add(section)

    subsection = SubSection(name=unit_name, section=section)
    ptype = ProblemType(code=f"NGD-{unit_name}", name=unit_name, subsection=subsection)
    session.add(ptype)
    session.flush()  # code unique 제약 확인 + id 채번

    cache[unit_name] = ptype
    return ptype


def _get_or_create_source(session: Session, cache: dict[int, Source], ngd_exam: sqlite3.Row) -> Source:
    exam_id = ngd_exam["id"]
    if exam_id in cache:
        return cache[exam_id]

    exam_name = f"{ngd_exam['year']} {ngd_exam['exam_type']}" if ngd_exam["exam_type"] else str(ngd_exam["year"])
    source = Source(
        school=ngd_exam["school"],
        exam_name=exam_name,
        year=int(ngd_exam["year"]) if ngd_exam["year"] and str(ngd_exam["year"]).isdigit() else None,
        region=ngd_exam["region"],
        material_kind="기출",
    )
    session.add(source)
    session.flush()

    cache[exam_id] = source
    return source


def import_from_ngd(ngd_db_path: Path, target_db_url: str) -> int:
    """NGD exam.db의 문제를 target_db_url이 가리키는 DB로 가져온다.
    이미 가져온 문제(ngd_problem_id로 식별)는 건너뛴다. 새로 들어온 문제 수를 반환한다."""
    ngd_conn = sqlite3.connect(f"file:{ngd_db_path}?mode=ro", uri=True)
    ngd_conn.row_factory = sqlite3.Row

    engine = init_db(target_db_url)
    with Session(engine) as session:
        already_imported = {
            pid for (pid,) in session.query(Problem.ngd_problem_id).filter(Problem.ngd_problem_id.isnot(None))
        }

        units_by_id = {row["id"]: row["name"] for row in ngd_conn.execute("SELECT id, name FROM units")}
        exams_by_id = {row["id"]: row for row in ngd_conn.execute("SELECT * FROM exams")}

        ptype_cache: dict[str, ProblemType] = {}
        source_cache: dict[int, Source] = {}

        imported = 0
        for row in ngd_conn.execute("SELECT * FROM problems"):
            if row["id"] in already_imported:
                continue

            unit_name = units_by_id.get(row["unit_id"], FALLBACK_UNIT_NAME)
            ptype = _get_or_create_problem_type(session, ptype_cache, unit_name)

            ngd_exam = exams_by_id.get(row["exam_id"])
            source = _get_or_create_source(session, source_cache, ngd_exam) if ngd_exam is not None else None

            problem = Problem(
                problem_type=ptype,
                source=source,
                stem_latex=_fix_latex(row["body"]) or "",
                answer=row["answer"],
                question_kind=row["qtype"] or "객관식",
                difficulty_label=row["difficulty"],
                original_file_path=ngd_exam["source_path"] if ngd_exam is not None else None,
                image_paths=row["image_paths"] if row["has_image"] else None,
                ngd_problem_id=row["id"],
            )
            session.add(problem)
            imported += 1

        session.commit()

    ngd_conn.close()
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ngd-db", type=Path, default=DEFAULT_NGD_DB, help="NGD exam.db 경로")
    parser.add_argument("--target", default="sqlite:///math_bank.db", help="가져올 대상 DB (SQLAlchemy URL)")
    args = parser.parse_args()

    count = import_from_ngd(args.ngd_db, args.target)
    print(f"{count}개 문제를 새로 가져왔습니다. (대상: {args.target})")


if __name__ == "__main__":
    main()
