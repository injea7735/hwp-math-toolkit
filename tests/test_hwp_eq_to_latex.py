import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hwp_eq_to_latex import hwp_eq_to_latex


def test_superscript_and_fraction():
    assert hwp_eq_to_latex("t ^{2} le{17} over {2}") == r"t^{2} \le \frac{17}{2}"


def test_sqrt_with_left_right_delimiters():
    result = hwp_eq_to_latex(
        "= sqrt{ left(2-t right)^{2}+ left(t- left(-2 right) right)^{2}}"
    )
    assert result == (
        r"= \sqrt{\left(2 - t\right)^{2} + \left(t - \left(- 2\right)\right)^{2}}"
    )


def test_bar_over_rm_collapses_to_overline():
    assert hwp_eq_to_latex("{ bar{rm{AB}it}}") == r"{\overline{AB}}"


def test_root_is_an_alias_for_sqrt():
    # 실제 HWP 수식 편집기가 내보내는 근호 토큰은 sqrt가 아니라 root다.
    assert hwp_eq_to_latex("=root{(t+1)^{2}+(t-1)^{2}}") == (
        r"= \sqrt{( t + 1 )^{2} + ( t - 1 )^{2}}"
    )


def test_rm_wrapping_bar_collapses_to_overline():
    # bar{rm{X}it} 뿐 아니라 반대 순서(rm bar{X}, 중괄호 없는 rm)도 overline이어야 한다.
    assert hwp_eq_to_latex("rm bar{AB}") == r"\overline{AB}"


def test_left_right_with_brace_delimiters_are_escaped():
    # \left{ 는 LaTeX 문법 오류다 -> \left\{ 로 이스케이프해야 한다.
    assert hwp_eq_to_latex("LEFT { x+1 RIGHT }") == r"\left\{x + 1\right\}"


def test_glued_repeated_keyword_is_split():
    # 공백 없이 붙어 나오는 경우가 실제 HWP 자료에서 확인됨(㉠, ㉡ 순서 표시 등).
    assert hwp_eq_to_latex("b=2a-3 cdotscdots") == r"b = 2 a - 3 \cdots \cdots"


def test_missing_trailing_close_brace_is_tolerated():
    # HWP 편집기가 스크립트 맨 끝의 '}' 를 저장하지 않는 경우가 실제 자료에서
    # 확인됨(커서를 밖으로 옮기면 편집기 UI가 자동으로 닫아버리는 듯).
    assert hwp_eq_to_latex("rm bar{AB}=root{10") == r"\overline{AB}=\sqrt{10}"


def test_uppercase_keyword_variants_are_recognized():
    # 실제 자료에서 CUP/IN/RM/OVER 처럼 명령어를 대문자로 쓴 경우가 확인됨.
    assert hwp_eq_to_latex("A CUP B") == r"A \cup B"
    assert hwp_eq_to_latex("x IN A") == r"x \in A"
    assert hwp_eq_to_latex("RM AB") == r"\mathrm{AB}"
    assert hwp_eq_to_latex("1 OVER 2") == r"\frac{1}{2}"


def test_uppercase_two_letter_keyword_not_confused_with_variable():
    # 짧은 키워드(to, pi, le 등)는 대문자로 나와도 그대로 변수명으로 남아야
    # 한다 - PI, TO 같은 두 글자짜리는 실제 점 이름을 이은 선분명일 수 있다.
    assert hwp_eq_to_latex("P TO Q") == r"P TO Q"


def test_new_symbols_from_real_data():
    assert hwp_eq_to_latex("A SMALLINTER B") == r"A \cap B"
    assert hwp_eq_to_latex("A TRIANGLE B") == r"A \triangle B"
    assert hwp_eq_to_latex("EMPTYSET") == r"\emptyset"
    assert hwp_eq_to_latex("x NOT IN A") == r"x \not \in A"


def test_glued_keyword_with_variable_suffix_is_split():
    # 실제 자료에서 확인됨: 'smallunionB smallunionC', 'barAB' 처럼
    # 키워드 바로 뒤에 변수명이 공백 없이 붙는 경우.
    assert hwp_eq_to_latex("A smallunionB") == r"A \cup B"
    assert hwp_eq_to_latex("barAB") == r"\bar{AB}"


def test_other_structural_mismatches_still_raise():
    # '}' 가 끝까지 안 나온 경우만 봐준다 - matrix/pile처럼 여는 괄호 자체가
    # 없는 진짜 구조 오류는 여전히 에러여야 한다.
    import pytest
    with pytest.raises(ValueError):
        hwp_eq_to_latex("matrix a#b")


def test_left_right_with_uppercase_keywords():
    result = hwp_eq_to_latex(
        "= LEFT ( 1-2t RIGHT ) ^{2} + LEFT ( -4t-3 RIGHT ) ^{2}"
    )
    assert result == r"= \left(1 - 2 t\right)^{2} + \left(- 4 t - 3\right)^{2}"


def test_therefore_symbol():
    assert hwp_eq_to_latex("therefore~ k=1") == r"\therefore ~ k = 1"


def test_rm_with_it_suffix():
    result = hwp_eq_to_latex("{rm{A}it} left(t,``-2 right)`")
    assert result == r"{\mathrm{A}} \left(t , \, \, - 2\right) \,"


def test_matrix_rows_and_columns():
    assert hwp_eq_to_latex("matrix{a & b # c & d}") == (
        r"\begin{matrix}a & b \\ c & d\end{matrix}"
    )


def test_pile_stacks_rows_without_columns():
    result = hwp_eq_to_latex("LEFT { pile{x+y=1 # x-y=2} RIGHT .")
    assert result == (
        r"\left\{\begin{matrix}x + y = 1 \\ x - y = 2\end{matrix}\right."
    )


def test_sum_with_sub_and_superscript_bounds():
    assert hwp_eq_to_latex("sum_{i=1}^{n} a_i") == r"\sum_{i = 1}^{n} a_{i}"


def test_integral_with_bounds():
    assert hwp_eq_to_latex("int_{a}^{b} f(x) dx") == r"\int_{a}^{b} f ( x ) dx"


def test_limit_with_bound():
    assert hwp_eq_to_latex("lim_{x to 0} f(x)") == r"\lim_{x \to 0} f ( x )"
