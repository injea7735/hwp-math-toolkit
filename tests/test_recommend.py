import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, Section, SubSection, ProblemType, Problem, Student, Attempt
from recommend import weak_problem_type_ids, globally_weak_problem_type_ids, pick_problems_for_student


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_type(session, code, name="유형"):
    chapter = Chapter(name=f"chapter-{code}")
    section = Section(name=f"section-{code}", chapter=chapter)
    subsection = SubSection(name=f"subsection-{code}", section=section)
    ptype = ProblemType(code=code, name=name, subsection=subsection)
    session.add(ptype)
    session.flush()
    return ptype


def _make_problems(session, ptype, count):
    problems = [Problem(problem_type=ptype, stem_latex=f"{ptype.code}-{i}") for i in range(count)]
    session.add_all(problems)
    session.flush()
    return problems


def _attempt(session, student, problem, is_correct, when):
    session.add(Attempt(student=student, problem=problem, is_correct=is_correct, answered_at=when))


def test_weak_problem_type_ids_ranks_lowest_accuracy_first(session):
    weak_type = _make_type(session, "T-101")
    strong_type = _make_type(session, "T-102")
    weak_problems = _make_problems(session, weak_type, 4)
    strong_problems = _make_problems(session, strong_type, 4)
    student = Student(name="철수")
    session.add(student)
    session.flush()

    base = datetime(2026, 1, 1)
    # weak_type: 1/4 correct
    for i, p in enumerate(weak_problems):
        _attempt(session, student, p, is_correct=(i == 0), when=base + timedelta(minutes=i))
    # strong_type: 4/4 correct
    for i, p in enumerate(strong_problems):
        _attempt(session, student, p, is_correct=True, when=base + timedelta(minutes=i))
    session.commit()

    ranked = weak_problem_type_ids(session, student.id, min_attempts=3)
    assert ranked == [weak_type.id, strong_type.id]


def test_type_with_too_few_attempts_excluded(session):
    ptype = _make_type(session, "T-201")
    problems = _make_problems(session, ptype, 2)
    student = Student(name="영희")
    session.add(student)
    session.flush()

    _attempt(session, student, problems[0], is_correct=False, when=datetime(2026, 1, 1))
    session.commit()

    assert weak_problem_type_ids(session, student.id, min_attempts=3) == []


def test_globally_weak_problem_type_ids_uses_all_students(session):
    hard_type = _make_type(session, "T-301")
    easy_type = _make_type(session, "T-302")
    hard_problems = _make_problems(session, hard_type, 3)
    easy_problems = _make_problems(session, easy_type, 3)

    students = [Student(name=f"student-{i}") for i in range(4)]
    session.add_all(students)
    session.flush()

    base = datetime(2026, 1, 1)
    for i, student in enumerate(students):
        # hard_type: mostly wrong across students
        _attempt(session, student, hard_problems[i % 3], is_correct=False, when=base)
        # easy_type: mostly right across students
        _attempt(session, student, easy_problems[i % 3], is_correct=True, when=base)
    session.commit()

    ranked = globally_weak_problem_type_ids(session, min_attempts=4)
    assert ranked == [hard_type.id, easy_type.id]


def test_pick_prefers_personal_weak_type(session):
    weak_type = _make_type(session, "T-401")
    strong_type = _make_type(session, "T-402")
    weak_problems = _make_problems(session, weak_type, 5)
    strong_problems = _make_problems(session, strong_type, 5)
    student = Student(name="철수")
    session.add(student)
    session.flush()

    base = datetime(2026, 1, 1)
    for i, p in enumerate(weak_problems[:4]):
        _attempt(session, student, p, is_correct=False, when=base + timedelta(minutes=i))
    for i, p in enumerate(strong_problems[:4]):
        _attempt(session, student, p, is_correct=True, when=base + timedelta(minutes=i))
    session.commit()

    picked = pick_problems_for_student(session, student.id, count=3, min_attempts=3)
    assert len(picked) == 3
    assert all(p.problem_type_id == weak_type.id for p in picked)


def test_pick_falls_back_to_globally_weak_type_when_no_personal_data(session):
    hard_type = _make_type(session, "T-501")
    other_type = _make_type(session, "T-502")
    hard_problems = _make_problems(session, hard_type, 4)
    _make_problems(session, other_type, 4)

    other_students = [Student(name=f"other-{i}") for i in range(4)]
    session.add_all(other_students)
    session.flush()

    base = datetime(2026, 1, 1)
    for i, s in enumerate(other_students):
        _attempt(session, s, hard_problems[i], is_correct=False, when=base)

    new_student = Student(name="신입")
    session.add(new_student)
    session.flush()
    session.commit()

    picked = pick_problems_for_student(
        session, new_student.id, count=2, min_attempts=3, global_min_attempts=4
    )
    assert len(picked) == 2
    assert all(p.problem_type_id == hard_type.id for p in picked)


def test_pick_deprioritizes_recently_correct_problem(session):
    ptype = _make_type(session, "T-601")
    problems = _make_problems(session, ptype, 3)  # p0: recently correct, p1/p2: unsolved
    student = Student(name="철수")
    session.add(student)
    session.flush()

    base = datetime(2026, 1, 1)
    # enough attempts (all on p0) to make this type count as "weak" despite mixed results
    _attempt(session, student, problems[0], is_correct=False, when=base)
    _attempt(session, student, problems[0], is_correct=False, when=base + timedelta(minutes=1))
    _attempt(session, student, problems[0], is_correct=True, when=base + timedelta(minutes=2))
    session.commit()

    picked = pick_problems_for_student(session, student.id, count=2, min_attempts=3)
    picked_ids = {p.id for p in picked}
    # p0 was last answered correctly -> should be deprioritized behind the untouched p1/p2
    assert picked_ids == {problems[1].id, problems[2].id}
