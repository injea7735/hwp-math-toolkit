import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, Section, SubSection, ProblemType, Problem
from hwp_workbook_parse import Problem as ParsedProblem
from import_workbook_problems import guess_question_kind, insert_problems


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def ptype(session):
    chapter = Chapter(name="공통수학2")
    section = Section(name="평면좌표", chapter=chapter)
    subsection = SubSection(name="평면좌표", section=section)
    pt = ProblemType(code="공통수학2-평면좌표-01", name="두 점 사이의 거리", subsection=subsection)
    session.add(pt)
    session.commit()
    return pt


def test_guess_question_kind():
    assert guess_question_kind("정답 ③") == "객관식"
    assert guess_question_kind("정답 풀이 참조") == "서술형"
    assert guess_question_kind("정답 3") == "단답형"


def test_insert_problems_creates_rows_linked_to_existing_type(session, ptype):
    parsed = [
        ParsedProblem(type_no="01", type_title="두 점 사이의 거리", seq=1,
                       answer="정답 ③", stem="두 점 $A$, $B$ 사이의 거리는?"),
    ]
    created, skipped = insert_problems(session, "공통수학2", "평면좌표", parsed, source_path="x.hwp")

    assert created == 1
    assert skipped == 0
    row = session.query(Problem).one()
    assert row.problem_type_id == ptype.id
    assert row.question_kind == "객관식"
    assert row.original_file_path == "x.hwp"


def test_insert_problems_skips_unknown_type(session, ptype):
    parsed = [
        ParsedProblem(type_no="99", type_title="존재하지 않는 유형", seq=1,
                       answer="정답 1", stem="stem"),
    ]
    created, skipped = insert_problems(session, "공통수학2", "평면좌표", parsed)

    assert created == 0
    assert skipped == 1
    assert session.query(Problem).count() == 0


def test_insert_problems_is_idempotent(session, ptype):
    parsed = [
        ParsedProblem(type_no="01", type_title="두 점 사이의 거리", seq=1,
                       answer="정답 ③", stem="같은 지문"),
    ]
    insert_problems(session, "공통수학2", "평면좌표", parsed)
    created, _ = insert_problems(session, "공통수학2", "평면좌표", parsed)

    assert created == 0
    assert session.query(Problem).count() == 1
