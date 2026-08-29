import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import Base, Chapter, DifficultyTier, Problem, ProblemType, Section, SubSection
from taxonomy_tree import (
    distinct_difficulty_labels,
    distinct_question_kinds,
    list_chapters,
    list_difficulty_tiers,
    list_sections,
    list_subsections,
    list_types,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def seeded(session):
    ch1 = Chapter(name="미적분1", order=2)
    ch2 = Chapter(name="공통수학1", order=1)
    session.add_all([ch1, ch2])
    session.flush()
    sec1 = Section(name="미분", chapter=ch1, order=1)
    sec2 = Section(name="적분", chapter=ch1, order=2)
    session.add_all([sec1, sec2])
    session.flush()
    ss1 = SubSection(name="함수의 극한", section=sec1, order=1)
    ss2 = SubSection(name="함수의 연속", section=sec1, order=2)
    session.add_all([ss1, ss2])
    session.flush()
    t1 = ProblemType(subsection=ss1, code="t1", name="극한값 구하기", order=1)
    t2 = ProblemType(subsection=ss2, code="t2", name="연속함수의 성질", order=1)
    session.add_all([t1, t2])
    session.flush()
    for i in range(3):
        session.add(Problem(problem_type=t1, stem_latex=f"극한 문제 {i}", question_kind="객관식"))
    session.add(Problem(problem_type=t2, stem_latex="연속 문제", question_kind="서술형", difficulty_label="중"))
    session.add(Problem(problem_type=t2, stem_latex="연속 문제2", question_kind="서술형", difficulty_label="하"))
    session.commit()
    return ch1, ch2, sec1, sec2, ss1, ss2, t1, t2


def test_list_chapters_ordered(session, seeded):
    result = list_chapters(session)
    assert [c["name"] for c in result] == ["공통수학1", "미적분1"]


def test_list_sections_scoped_to_chapter(session, seeded):
    result = list_sections(session, "미적분1")
    assert [s["name"] for s in result] == ["미분", "적분"]
    assert list_sections(session, "공통수학1") == []


def test_list_subsections_filters_by_section(session, seeded):
    result = list_subsections(session, "미적분1")
    assert [s["name"] for s in result] == ["함수의 극한", "함수의 연속"]
    filtered = list_subsections(session, "미적분1", section_names=["적분"])
    assert filtered == []


def test_list_types_includes_problem_count(session, seeded):
    result = list_types(session, "미적분1")
    by_name = {t["name"]: t["problem_count"] for t in result}
    assert by_name == {"극한값 구하기": 3, "연속함수의 성질": 2}


def test_list_types_filters_by_subsection(session, seeded):
    result = list_types(session, "미적분1", subsection_names=["함수의 연속"])
    assert [t["name"] for t in result] == ["연속함수의 성질"]


def test_list_difficulty_tiers(session):
    session.add_all([DifficultyTier(name="심화 유형", order=2), DifficultyTier(name="핵심 유형", order=1)])
    session.commit()
    result = list_difficulty_tiers(session)
    assert [t["name"] for t in result] == ["핵심 유형", "심화 유형"]


def test_distinct_difficulty_labels_sorted_and_deduped(session, seeded):
    result = distinct_difficulty_labels(session, "미적분1")
    assert result == ["하", "중"]


def test_distinct_question_kinds(session, seeded):
    result = distinct_question_kinds(session, "미적분1")
    assert result == ["객관식", "서술형"]
