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
        r"\left{\begin{matrix}x + y = 1 \\ x - y = 2\end{matrix}\right."
    )


def test_sum_with_sub_and_superscript_bounds():
    assert hwp_eq_to_latex("sum_{i=1}^{n} a_i") == r"\sum_{i = 1}^{n} a_{i}"


def test_integral_with_bounds():
    assert hwp_eq_to_latex("int_{a}^{b} f(x) dx") == r"\int_{a}^{b} f ( x ) dx"


def test_limit_with_bound():
    assert hwp_eq_to_latex("lim_{x to 0} f(x)") == r"\lim_{x \to 0} f ( x )"
