import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import Base, Chapter, Section, SubSection, ProblemType, Problem
from worksheet_select import WorksheetSelection, select_problems, describe_problem_path


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def seeded(session):
    ch = Chapter(name="미적분1")
    session.add(ch)
    session.flush()
    sec = Section(name="미분", chapter=ch)
    session.add(sec)
    session.flush()
    ss1 = SubSection(name="함수의 극한", section=sec, order=1)
    ss2 = SubSection(name="함수의 연속", section=sec, order=2)
    session.add_all([ss1, ss2])
    session.flush()
    t1 = ProblemType(subsection=ss1, code="t1", name="극한값 구하기", order=1)
    t2 = ProblemType(subsection=ss2, code="t2", name="연속함수의 성질", order=1)
    session.add_all([t1, t2])
    session.flush()
    for i in range(3):
        session.add(Problem(problem_type=t1, stem_latex=f"극한 문제 {i}"))
    for i in range(2):
        session.add(Problem(problem_type=t2, stem_latex=f"연속 문제 {i}"))
    session.commit()
    return ch, ss1, ss2, t1, t2


@pytest.fixture
def seeded_with_difficulty(session, seeded):
    ch, ss1, ss2, t1, t2 = seeded
    for label in ["하", "하", "중", "중", "중", "상", "상", "상", "상", "상"]:
        session.add(Problem(problem_type=t1, stem_latex="난이도 문제", difficulty_label=label, question_kind="객관식"))
    session.add(Problem(problem_type=t2, stem_latex="서술형 문제", question_kind="서술형"))
    session.commit()
    return ch, ss1, ss2, t1, t2


def test_filters_by_chapter_only(session, seeded):
    sel = WorksheetSelection(chapter="미적분1")
    result = select_problems(session, sel)
    assert len(result) == 5


def test_filters_by_subsection(session, seeded):
    sel = WorksheetSelection(chapter="미적분1", subsections=["함수의 극한"])
    result = select_problems(session, sel)
    assert len(result) == 3
    assert all(p.problem_type.subsection.name == "함수의 극한" for p in result)


def test_filters_by_type_name_substring(session, seeded):
    sel = WorksheetSelection(chapter="미적분1", type_names=["연속함수"])
    result = select_problems(session, sel)
    assert len(result) == 2


def test_count_truncates(session, seeded):
    sel = WorksheetSelection(chapter="미적분1", count=2)
    result = select_problems(session, sel)
    assert len(result) == 2


def test_unknown_chapter_returns_empty(session, seeded):
    sel = WorksheetSelection(chapter="존재안함")
    assert select_problems(session, sel) == []


def test_describe_problem_path(session, seeded):
    _, ss1, _, t1, _ = seeded
    p = session.query(Problem).filter_by(problem_type=t1).first()
    path = describe_problem_path(p)
    assert path == "미적분1 > 미분 > 함수의 극한 > 극한값 구하기"


def test_filters_by_question_kind(session, seeded_with_difficulty):
    sel = WorksheetSelection(chapter="미적분1", question_kinds=["서술형"])
    result = select_problems(session, sel)
    assert len(result) == 1
    assert result[0].question_kind == "서술형"


def test_difficulty_ratio_allocates_proportionally(session, seeded_with_difficulty):
    # 풀: 하=2, 중=3, 상=5. 요청 비율 하:2 중:5 상:3 -> 정확한 목표는
    # 하=2,중=5,상=3 이지만 중은 3개뿐이라 2개 부족 -> 그 2개는 상의 여유분(5-3=2)에서 채워진다.
    sel = WorksheetSelection(
        chapter="미적분1",
        question_kinds=["객관식"],
        count=10,
        difficulty_ratio={"하": 2, "중": 5, "상": 3},
        seed=1,
    )
    result = select_problems(session, sel)
    assert len(result) == 10
    counts = {}
    for p in result:
        counts[p.difficulty_label] = counts.get(p.difficulty_label, 0) + 1
    assert counts == {"하": 2, "중": 3, "상": 5}


def test_difficulty_ratio_sum_matches_requested_count():
    from worksheet_select import _allocate_ratio_counts
    result = _allocate_ratio_counts(10, {"a": 1, "b": 1, "c": 1})
    assert sum(result.values()) == 10
