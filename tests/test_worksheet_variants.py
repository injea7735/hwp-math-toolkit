import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import Base, Problem
from worksheet_variants import make_variants


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _mc_problem(session, answer_mark: str, choices: list[str]) -> Problem:
    p = Problem(
        stem_latex="테스트 문제",
        choices_latex=json.dumps(choices, ensure_ascii=False),
        answer=answer_mark,
        question_kind="객관식",
    )
    session.add(p)
    session.commit()
    return p


def test_no_forms_given_name_produces_one_variant(session):
    p = _mc_problem(session, "①", ["가", "나", "다"])
    variants = make_variants([p], [""], shuffle_problem_order=False, shuffle_choices=False)
    assert len(variants) == 1
    assert variants[0].name == ""
    assert variants[0].choice_orders == [None]
    assert variants[0].display_answers == ["①"]


def test_shuffling_choices_remaps_answer_to_new_position(session):
    p = _mc_problem(session, "②", ["가", "나", "다", "라"])  # 정답은 원래 인덱스 1("나")
    variants = make_variants([p], ["A"], shuffle_problem_order=False, shuffle_choices=True, seed=42)
    v = variants[0]
    order = v.choice_orders[0]
    assert order is not None
    # 정답으로 표시된 새 위치가 실제로 원래 정답 내용("나", 인덱스 1)을 가리켜야 한다
    from worksheet_variants import _CIRCLED
    new_pos = _CIRCLED.index(v.display_answers[0])
    assert order[new_pos] == 1


def test_two_forms_are_independently_shuffled(session):
    problems = [_mc_problem(session, "①", ["가", "나", "다", "라", "마"]) for _ in range(5)]
    variants = make_variants(problems, ["A", "B"], seed=1)
    assert [v.name for v in variants] == ["A", "B"]
    # 최소한 문제 순서 또는 보기 순서 중 하나는 서로 달라야 한다 (완전 동일 확률은 매우 낮음)
    a_ids = [p.id for p in variants[0].problems]
    b_ids = [p.id for p in variants[1].problems]
    a_orders = variants[0].choice_orders
    b_orders = variants[1].choice_orders
    assert a_ids != b_ids or a_orders != b_orders


def test_non_multiple_choice_problem_answer_unchanged(session):
    p = Problem(stem_latex="단답형 문제", answer="7", question_kind="단답형")
    session.add(p)
    session.commit()
    variants = make_variants([p], ["A"], shuffle_choices=True, seed=1)
    assert variants[0].choice_orders == [None]
    assert variants[0].display_answers == ["7"]
