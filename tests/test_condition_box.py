import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from condition_box import split_condition_block


def test_no_conditions_returns_text_unchanged():
    text = "함수 f(x)=x^2에 대하여 f(1)의 값은?"
    main, items, trailing = split_condition_block(text)
    assert main == text
    assert items is None
    assert trailing == ""


def test_splits_two_conditions():
    text = (
        "함수 g(x)가 다음 조건을 만족시킬 때, 극솟값은? [4.2점]\n"
        "(가) 집합의 원소의 개수는 2이다.(나) 함수 g(x)는 극댓값을 갖지 않는다."
    )
    main, items, trailing = split_condition_block(text)
    assert main == "함수 g(x)가 다음 조건을 만족시킬 때, 극솟값은? [4.2점]"
    assert items == [
        "(가) 집합의 원소의 개수는 2이다.",
        "(나) 함수 g(x)는 극댓값을 갖지 않는다.",
    ]
    assert trailing == ""


def test_splits_three_conditions_with_newlines():
    text = "본문\n(가) 첫째\n(나) 둘째\n(다) 셋째"
    main, items, trailing = split_condition_block(text)
    assert main == "본문"
    assert items == ["(가) 첫째", "(나) 둘째", "(다) 셋째"]
    assert trailing == ""


def test_trailing_question_after_conditions_is_not_swallowed():
    # 실제 DB에 있는 패턴: 조건 목록 바로 뒤에 개행으로 구분된 실제 질문
    # 문장이 이어진다. 이 질문이 마지막 조건 항목 안으로 삼켜지면 안 된다.
    text = (
        "함수 f(x)와 g(t)는 다음 조건을 만족시킨다.\n"
        "(가) f(1)=2 (나) 함수 g(t)는 실수 전체의 집합에서 미분가능하다.\n"
        "f(2)의 값은? (단, a,b는 상수이다.) [4.8점]"
    )
    main, items, trailing = split_condition_block(text)
    assert main == "함수 f(x)와 g(t)는 다음 조건을 만족시킨다."
    assert items == [
        "(가) f(1)=2",
        "(나) 함수 g(t)는 실수 전체의 집합에서 미분가능하다.",
    ]
    assert trailing == "f(2)의 값은? (단, a,b는 상수이다.) [4.8점]"
