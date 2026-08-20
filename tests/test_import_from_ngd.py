import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from import_from_ngd import import_from_ngd
from models import Problem, Source, SubSection, init_db
from sqlalchemy.orm import Session


def _make_ngd_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE units(id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE exams(id INTEGER PRIMARY KEY, filename TEXT, source_path TEXT,
          school_level TEXT, year TEXT, grade INTEGER, semester INTEGER, exam_type TEXT,
          region TEXT, school TEXT, course TEXT);
        CREATE TABLE problems(id INTEGER PRIMARY KEY, exam_id INTEGER, seq INTEGER,
          body TEXT, explanation TEXT, answer TEXT, unit_id INTEGER, difficulty TEXT,
          has_image INTEGER, image_paths TEXT, qtype TEXT);
        """
    )
    con.execute("INSERT INTO units VALUES (1, '함수의 극한')")
    con.execute(
        "INSERT INTO exams VALUES (1, 'a.hwpx', 'C:/src/a.hwpx', '고등학교', '2025', 2, 2, "
        "'중간고사', '강원원주시', '원주여고', '수학2')"
    )
    con.execute(
        "INSERT INTO problems VALUES (1, 1, 1, "
        r"'$\lim_{x->\infty}{x}$', '[정답] ①', '①', 1, '하', 0, NULL, '객관식')"
    )
    con.execute(
        "INSERT INTO problems VALUES (2, 1, 2, "
        "'삽화가 있는 문제', '[정답] ②', '②', 1, '중', 1, "
        '\'["C:/imgs/1.bmp"]\', \'서술형\')'
    )
    con.commit()
    con.close()


@pytest.fixture
def ngd_db(tmp_path) -> Path:
    path = tmp_path / "exam.db"
    _make_ngd_db(path)
    return path


def test_import_creates_placeholder_taxonomy_and_problems(ngd_db, tmp_path):
    target = f"sqlite:///{tmp_path / 'target.db'}"
    imported = import_from_ngd(ngd_db, target)
    assert imported == 2

    engine = init_db(target)
    with Session(engine) as session:
        assert session.query(Problem).count() == 2

        subsection = session.query(SubSection).filter_by(name="함수의 극한").one()
        assert subsection.problem_types[0].problems[0].ngd_problem_id in {1, 2}

        objective = session.query(Problem).filter_by(ngd_problem_id=1).one()
        assert objective.stem_latex == r"$\lim_{x\to\infty}{x}$"  # -> 가 \to 로 치환됨
        assert objective.question_kind == "객관식"
        assert objective.source.school == "원주여고"
        assert objective.image_paths is None

        essay = session.query(Problem).filter_by(ngd_problem_id=2).one()
        assert essay.question_kind == "서술형"
        assert essay.image_paths == '["C:/imgs/1.bmp"]'


def test_import_is_idempotent(ngd_db, tmp_path):
    target = f"sqlite:///{tmp_path / 'target.db'}"
    first = import_from_ngd(ngd_db, target)
    second = import_from_ngd(ngd_db, target)

    assert first == 2
    assert second == 0

    engine = init_db(target)
    with Session(engine) as session:
        assert session.query(Problem).count() == 2
        assert session.query(Source).count() == 1


def test_problem_with_unknown_unit_falls_back(tmp_path):
    ngd_path = tmp_path / "exam.db"
    con = sqlite3.connect(ngd_path)
    con.executescript(
        """
        CREATE TABLE units(id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE exams(id INTEGER PRIMARY KEY, filename TEXT, source_path TEXT,
          school_level TEXT, year TEXT, grade INTEGER, semester INTEGER, exam_type TEXT,
          region TEXT, school TEXT, course TEXT);
        CREATE TABLE problems(id INTEGER PRIMARY KEY, exam_id INTEGER, seq INTEGER,
          body TEXT, explanation TEXT, answer TEXT, unit_id INTEGER, difficulty TEXT,
          has_image INTEGER, image_paths TEXT, qtype TEXT);
        """
    )
    con.execute(
        "INSERT INTO problems VALUES (1, NULL, 1, '본문', NULL, NULL, NULL, NULL, 0, NULL, NULL)"
    )
    con.commit()
    con.close()

    target = f"sqlite:///{tmp_path / 'target.db'}"
    imported = import_from_ngd(ngd_path, target)
    assert imported == 1

    engine = init_db(target)
    with Session(engine) as session:
        subsection = session.query(SubSection).filter_by(name="미분류").one()
        assert subsection.problem_types[0].problems[0].ngd_problem_id == 1
