import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, Problem
from pdf_sumaessing_extract import SumProblem
from import_sumaessing_problems import insert_problems


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def chapter(session):
    ch = Chapter(name="미적분2")
    session.add(ch)
    session.commit()
    return ch


def test_insert_creates_ordinal_type_under_real_subsection(session, chapter):
    parsed = [
        SumProblem(number="0001", section_name="수열의 극한", subsection_name="수열의 극한",
                   type_seq=1, level="2", page_index=7,
                   image_path="img/0001.png", text="stem"),
    ]
    created = insert_problems(session, parsed, pdf_path="x.pdf")

    assert created == 1
    row = session.query(Problem).one()
    assert row.problem_type.name == "유형 1"
    assert row.problem_type.subsection.name == "수열의 극한"
    assert row.difficulty_tier.name == "Level 2"
    assert json.loads(row.image_paths) == ["img/0001.png"]


def test_insert_is_idempotent(session, chapter):
    parsed = [
        SumProblem(number="0001", section_name="수열의 극한", subsection_name="수열의 극한",
                   type_seq=1, level=None, page_index=7,
                   image_path="img/0001.png", text="stem"),
    ]
    insert_problems(session, parsed, pdf_path="x.pdf")
    created = insert_problems(session, parsed, pdf_path="x.pdf")

    assert created == 0
    assert session.query(Problem).count() == 1


def test_insert_handles_missing_level(session, chapter):
    parsed = [
        SumProblem(number="0001", section_name="수열의 극한", subsection_name="수열의 극한",
                   type_seq=1, level=None, page_index=7,
                   image_path="img/0001.png", text="stem"),
    ]
    insert_problems(session, parsed, pdf_path="x.pdf")
    row = session.query(Problem).one()
    assert row.difficulty_tier is None
