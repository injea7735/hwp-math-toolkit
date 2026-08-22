import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, DifficultyTier, Problem
from pdf_problem_extract import ExtractedProblem
from import_pdf_problems import insert_pdf_problems


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def setup(session):
    session.add(Chapter(name="대수"))
    session.add(DifficultyTier(name="핵심 유형", order=1))
    session.commit()


def test_insert_pdf_problems_creates_placeholder_type_and_links_tier(session, setup):
    parsed = [
        ExtractedProblem(number="001", section_index=0, tier_name="핵심 유형",
                          page_index=9, image_path="img/001.png", text="8의 세제곱근을 모두 구하시오."),
    ]
    created = insert_pdf_problems(session, "대수", ["지수함수와 로그함수"], parsed, "x.pdf")

    assert created == 1
    row = session.query(Problem).one()
    assert row.problem_type.subsection.section.name == "지수함수와 로그함수"
    assert row.difficulty_tier.name == "핵심 유형"
    assert json.loads(row.image_paths) == ["img/001.png"]
    assert row.answer is None


def test_insert_pdf_problems_is_idempotent(session, setup):
    parsed = [
        ExtractedProblem(number="001", section_index=0, tier_name="핵심 유형",
                          page_index=9, image_path="img/001.png", text="stem"),
    ]
    insert_pdf_problems(session, "대수", ["지수함수와 로그함수"], parsed, "x.pdf")
    created = insert_pdf_problems(session, "대수", ["지수함수와 로그함수"], parsed, "x.pdf")

    assert created == 0
    assert session.query(Problem).count() == 1


def test_insert_pdf_problems_handles_missing_tier(session, setup):
    # 대단원 도입부를 못 지나 tier_name이 아직 None인 경우도 있어야 안 죽는다.
    parsed = [
        ExtractedProblem(number="001", section_index=0, tier_name=None,
                          page_index=1, image_path="img/001.png", text="stem"),
    ]
    created = insert_pdf_problems(session, "대수", ["지수함수와 로그함수"], parsed, "x.pdf")

    assert created == 1
    row = session.query(Problem).one()
    assert row.difficulty_tier is None
