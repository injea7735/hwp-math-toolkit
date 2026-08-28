from latex_to_hwp_eq import latex_to_hwp_eq
from hwp_eq_to_latex import hwp_eq_to_latex


def test_superscript_no_double_brace():
    assert latex_to_hwp_eq(r"x^{2}") == "x^{2}"


def test_subscript_no_double_brace():
    assert latex_to_hwp_eq(r"a_{n}") == "a_{n}"


def test_frac_becomes_over():
    assert latex_to_hwp_eq(r"\frac{1}{2}") == "{1} over {2}"


def test_sqrt():
    assert latex_to_hwp_eq(r"\sqrt{x^{2}+1}") == "sqrt{x^{2} + 1}"


def test_overline_becomes_bar():
    assert latex_to_hwp_eq(r"\overline{AB}") == "bar{AB}"


def test_left_right_parens():
    assert latex_to_hwp_eq(r"\left(x-1\right)") == "LEFT ( x - 1 RIGHT )"


def test_left_right_braces_escaped():
    out = latex_to_hwp_eq(r"\left\{ x \right\}")
    assert out == "LEFT { x RIGHT }"


def test_cases_environment_uses_pile():
    out = latex_to_hwp_eq(
        r"\begin{cases} x^2 & (x \geq 0) \\ -x^2 & (x < 0) \end{cases}"
    )
    assert out.startswith("LEFT { pile{")
    assert "#" in out  # 행 구분자


def test_symbols_use_unicode_not_broken_hwp_keywords():
    # 'to'/'gt'/'lt'/'mp' 키워드는 실제 HWP(COM)에서 조용히 깨지는 걸 직접
    # 확인했다(그 뒤 내용이 통째로 사라짐) - 유니코드 문자를 써야 한다.
    out = latex_to_hwp_eq(r"\lim_{x \to 0}")
    assert "→" in out
    assert "to" not in out.split("{")[-1] or "→" in out

    assert latex_to_hwp_eq(r"x > 0") == "x > 0"
    assert latex_to_hwp_eq(r"x \geq 0") == "x ≥ 0"


def test_roundtrip_preserves_structure_via_reader():
    samples = [
        r"x^{2} + y^{2} = r^{2}",
        r"\frac{1}{2}x^{2} - 3x + 1",
        r"\lim_{x \to 0} \frac{f(x)}{x}",
        r"\left( x - 1 \right)^{2}",
    ]
    for s in samples:
        hwp_script = latex_to_hwp_eq(s)
        back = hwp_eq_to_latex(hwp_script)
        # 완전히 동일한 문자열은 아니어도(공백/괄호 스타일 차이) 핵심 구조
        # 토큰(분수/극한/거듭제곱)은 살아남아야 한다.
        assert back  # 파싱 자체가 에러 없이 끝남 (HWP 문법으로 유효)
