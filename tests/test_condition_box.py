from condition_box import split_condition_block


def test_no_conditions_returns_text_unchanged():
    text = "함수 f(x)=x^2에 대하여 f(1)의 값은?"
    main, items = split_condition_block(text)
    assert main == text
    assert items is None


def test_splits_two_conditions():
    text = (
        "함수 g(x)가 다음 조건을 만족시킬 때, 극솟값은? [4.2점]\n"
        "(가) 집합의 원소의 개수는 2이다.(나) 함수 g(x)는 극댓값을 갖지 않는다."
    )
    main, items = split_condition_block(text)
    assert main == "함수 g(x)가 다음 조건을 만족시킬 때, 극솟값은? [4.2점]"
    assert items == [
        "(가) 집합의 원소의 개수는 2이다.",
        "(나) 함수 g(x)는 극댓값을 갖지 않는다.",
    ]


def test_splits_three_conditions_with_newlines():
    text = "본문\n(가) 첫째\n(나) 둘째\n(다) 셋째"
    main, items = split_condition_block(text)
    assert main == "본문"
    assert items == ["(가) 첫째", "(나) 둘째", "(다) 셋째"]
