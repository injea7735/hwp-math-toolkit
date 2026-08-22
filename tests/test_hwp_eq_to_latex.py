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
