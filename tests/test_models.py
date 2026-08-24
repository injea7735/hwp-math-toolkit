import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, Section, SubSection, ProblemType, Concept, Problem, Source


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_create_all_tables():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert tables == {
        "chapters", "sections", "subsections", "problem_types",
        "difficulty_tiers", "concepts", "problem_concepts", "sources",
        "problems", "students", "attempts",
    }


def test_taxonomy_chain_relationships(session):
    chapter = Chapter(name="미적분Ⅰ")
    section = Section(name="지수함수와 로그함수", chapter=chapter)
    subsection = SubSection(name="지수함수의 그래프", section=section)
    ptype = ProblemType(code="T-201", name="지수함수 그래프 개형 판별", subsection=subsection)
    session.add(ptype)
    session.commit()

    fetched = session.query(Chapter).filter_by(name="미적분Ⅰ").one()
    assert fetched.sections[0].subsections[0].problem_types[0].code == "T-201"
    assert ptype.subsection.section.chapter.name == "미적분Ⅰ"


def test_duplicate_section_name_in_same_chapter_rejected(session):
    chapter = Chapter(name="확률과 통계")
    session.add_all([
        Section(name="조건부확률", chapter=chapter),
        Section(name="조건부확률", chapter=chapter),
    ])
    with pytest.raises(IntegrityError):
        session.commit()


def test_same_section_name_allowed_in_different_chapters(session):
    chapter_a = Chapter(name="공통수학1")
    chapter_b = Chapter(name="공통수학2")
    session.add_all([
        Section(name="이차방정식", chapter=chapter_a),
        Section(name="이차방정식", chapter=chapter_b),
    ])
    session.commit()

    assert session.query(Section).filter_by(name="이차방정식").count() == 2


def test_problem_concepts_many_to_many(session):
    chapter = Chapter(name="공통수학1")
    section = Section(name="방정식과 부등식", chapter=chapter)
    subsection = SubSection(name="이차방정식", section=section)
    ptype = ProblemType(code="T-101", name="이차방정식의 근의 판별", subsection=subsection)
    problem = Problem(
        problem_type=ptype,
        stem_latex=r"x^2 - 5x + 6 = 0",
        concepts=[Concept(name="이차방정식"), Concept(name="근의 공식")],
    )
    session.add(problem)
    session.commit()

    fetched = session.query(Problem).one()
    assert {c.name for c in fetched.concepts} == {"이차방정식", "근의 공식"}


def test_problem_source_is_optional(session):
    chapter = Chapter(name="공통수학1")
    section = Section(name="방정식과 부등식", chapter=chapter)
    subsection = SubSection(name="이차방정식", section=section)
    ptype = ProblemType(code="T-102", name="이차부등식", subsection=subsection)
    problem = Problem(problem_type=ptype, stem_latex="...")
    session.add(problem)
    session.commit()

    assert problem.source is None


def test_problem_with_source(session):
    chapter = Chapter(name="공통수학1")
    section = Section(name="방정식과 부등식", chapter=chapter)
    subsection = SubSection(name="이차방정식", section=section)
    ptype = ProblemType(code="T-103", name="이차방정식 활용", subsection=subsection)
    source = Source(school="대일고", exam_name="2025 중간고사", year=2025)
    problem = Problem(problem_type=ptype, stem_latex="...", source=source)
    session.add(problem)
    session.commit()

    assert problem.source.school == "대일고"
    assert source.problems[0] is problem
