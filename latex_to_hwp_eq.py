"""LaTeX 수식 -> HWP 수식 편집기 스크립트(DSL) 변환기.

hwp_eq_to_latex.py(HWP eqedit DSL -> LaTeX)의 역방향. 우리 DB의 stem_latex는
이 프로젝트 자체의 hwp_eq_to_latex.py로 만들어졌거나(HWP 원본 소스), NGD가
자체 변환한 것(기출 문제)이라 두 방언이 섞여 있다. 자동 출제(Pillar 3)에서
문제를 실제 HWP 수식 객체로 삽입하기 위해 필요한 고빈도 구문만 다룬다
(전체 LaTeX 문법의 완전한 역변환은 목표가 아님).

기호는 HWP eqedit 키워드(gt/lt/to/mp 등)로 텍스트 매핑하지 않고 유니코드
문자를 직접 eq.string에 심는다 - 실제 HWP(COM 자동화)로 직접 검증해보니
'to'/'gt'/'lt'/'mp' 같은 일부 키워드는 조용히 깨지지만(그 뒤 내용이 통째로
사라짐) 유니코드 기호(→ ≤ ≥ × ± 등)는 전부 정상 렌더링된다. 유니코드가
안 통하는 건 구조적 문법(over/sqrt/bar/matrix/pile/LEFT·RIGHT/^/_)뿐이라
이것들만 실제 HWP 키워드를 쓴다.
"""
from __future__ import annotations
import re

# LaTeX 명령 -> 유니코드 문자. 전부 실제 HWP(COM EquationCreate)로 직접
# 렌더링 확인함 (scratchpad/test_unicode_batch.py, 2026-08-28).
_LATEX_TO_UNICODE: dict[str, str] = {
    r'\to': '→', r'\rightarrow': '→', r'\Rightarrow': '→',
    r'\leftarrow': '←', r'\Leftarrow': '←',
    r'\le': '≤', r'\leq': '≤', r'\ge': '≥', r'\geq': '≥', r'\ne': '≠', r'\neq': '≠',
    r'\in': '∈', r'\notin': '∉', r'\cap': '∩', r'\cup': '∪',
    r'\subset': '⊂', r'\supset': '⊃',
    r'\times': '×', r'\div': '÷', r'\pm': '±', r'\mp': '∓', r'\cdot': '·',
    r'\infty': '∞', r'\partial': '∂', r'\nabla': '∇',
    r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ', r'\theta': 'θ',
    r'\pi': 'π', r'\phi': 'φ', r'\omega': 'ω',
    r'\angle': '∠', r'\perp': '⊥', r'\parallel': '∥',
    r'\sim': '∼', r'\approx': '≈', r'\equiv': '≡',
    r'\circ': '∘', r'\ast': '∗', r'\triangle': '△', r'\emptyset': '∅',
    r'\therefore': '∴', r'\because': '∵',
    r'\cdots': '⋯', r'\vdots': '⋮', r'\ddots': '⋱', r'\ldots': '…',
    r'\mid': '|', r'\deg': '°',
}

# 구조 키워드(HWP eqedit 실제 문법). sum/int/lim/prod은 그대로 텍스트로 두면
# HWP가 자체적으로 연산자 기호+아래/위첨자 배치를 해준다 (^ _ 뒤에 오는 값과
# 결합해서 sigma/integral 모양을 그린다).
_STRUCT_KEYWORDS = {r'\sum': 'sum', r'\prod': 'prod', r'\int': 'int', r'\lim': 'lim'}

_LATEX_COMMANDS = sorted(
    list(_LATEX_TO_UNICODE) + list(_STRUCT_KEYWORDS), key=len, reverse=True
)

_TOKEN_RE = re.compile(
    r'\\left|\\right|\\begin|\\end|\\frac|\\dfrac|\\sqrt|\\overline|\\bar|\\mathrm'
    r'|\\text|\\{|\\}|\\' + r'|\\'.join(re.escape(c[1:]) for c in _LATEX_COMMANDS)
    + r'|[{}^_&]|\\\\|\\,|\\!|\\ |[A-Za-z]+|[0-9]+(?:\.[0-9]+)?|\S'
)


def _tokenize(latex: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(latex) if t.strip() != '']


class _Parser:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self):
        t = self.peek()
        self.pos += 1
        return t

    def expect(self, tok):
        t = self.next()
        if t != tok:
            raise ValueError(f"'{tok}' 예상했지만 '{t}' 나옴 (위치 {self.pos})")

    def parse_group_raw(self) -> str:
        self.expect('{')
        inner = self.parse_sequence({'}'})
        self.expect('}')
        return inner

    @staticmethod
    def _strip_braces(s: str) -> str:
        s = s.strip()
        if s.startswith('{') and s.endswith('}'):
            return s[1:-1]
        return s

    def parse_sequence(self, stop: set[str]) -> str:
        parts: list[str] = []
        while self.peek() is not None and self.peek() not in stop:
            t = self.peek()

            if t == '^':
                self.next()
                sup = self._strip_braces(self.parse_atom())
                if parts:
                    parts[-1] = parts[-1] + '^{' + sup + '}'
                else:
                    parts.append('^{' + sup + '}')
                continue

            if t == '_':
                self.next()
                sub = self._strip_braces(self.parse_atom())
                if parts:
                    parts[-1] = parts[-1] + '_{' + sub + '}'
                else:
                    parts.append('_{' + sub + '}')
                continue

            if t in (r'\frac', r'\dfrac'):
                self.next()
                numer = self.parse_group_raw()
                denom = self.parse_group_raw()
                parts.append('{' + numer + '} over {' + denom + '}')
                continue

            parts.append(self.parse_atom())

        return ' '.join(p for p in parts if p != '')

    _DELIM_MAP = {r'\{': '{', r'\}': '}', '.': '.'}

    def _hwp_delim(self) -> str:
        t = self.next()
        return self._DELIM_MAP.get(t, t)

    def parse_atom(self) -> str:
        t = self.peek()

        if t == '{':
            return '{' + self.parse_group_raw() + '}'

        if t == r'\sqrt':
            self.next()
            inner = self.parse_group_raw()
            return 'sqrt{' + inner + '}'

        if t in (r'\overline', r'\bar'):
            self.next()
            inner = self.parse_group_raw()
            return 'bar{' + inner + '}'

        if t in (r'\mathrm', r'\text'):
            self.next()
            inner = self.parse_group_raw()
            return 'rm{' + inner + '}it'

        if t == r'\left':
            self.next()
            open_d = self._hwp_delim()
            inner = self.parse_sequence({r'\right'})
            self.expect(r'\right')
            close_d = self._hwp_delim()
            return f'LEFT {open_d} {inner} RIGHT {close_d}'

        if t == r'\begin':
            self.next()
            env = self.parse_group_raw()
            return self._parse_env(env)

        if t in (r'\,', r'\!'):
            self.next()
            return '`'

        if t == r'\\':
            self.next()
            return '#'

        if t in _STRUCT_KEYWORDS:
            self.next()
            return _STRUCT_KEYWORDS[t]

        if t in _LATEX_TO_UNICODE:
            self.next()
            return _LATEX_TO_UNICODE[t]

        if t and t.startswith('\\'):
            # 알 수 없는 명령어: 백슬래시만 떼고 원문 그대로 통과시킨다
            self.next()
            return t[1:]

        self.next()
        return t

    def _parse_env(self, env: str) -> str:
        rows: list[list[str]] = [[]]
        env = env.strip()
        while True:
            if self.peek() == r'\end':
                break
            if self.peek() == '&':
                self.next()
                rows[-1].append('')
                continue
            if self.peek() == r'\\':
                self.next()
                rows.append([])
                continue
            cell = self.parse_atom()
            if rows[-1] and rows[-1][-1] == '':
                rows[-1][-1] = cell
            elif rows[-1]:
                rows[-1][-1] = rows[-1][-1] + ' ' + cell
            else:
                rows[-1].append(cell)
        self.expect(r'\end')
        self.parse_group_raw()

        row_strs = []
        for row in rows:
            if not row:
                continue
            if env == 'matrix' and len(row) > 1:
                row_strs.append(' & '.join(c for c in row))
            else:
                row_strs.append(' '.join(c for c in row))
        body = ' # '.join(row_strs)

        if env == 'cases':
            return 'LEFT { pile{ ' + body + ' } RIGHT .'
        return 'matrix{ ' + body + ' }'


def latex_to_hwp_eq(latex: str) -> str:
    """LaTeX 수식 문자열(양끝 $ 없이)을 HWP eqedit 스크립트로 변환한다."""
    latex = latex.strip()
    tokens = _tokenize(latex)
    parser = _Parser(tokens)
    return parser.parse_sequence(set())


if __name__ == '__main__':
    samples = [
        r"x^{2} + y^{2} = r^{2}",
        r"\frac{1}{2}x^{2} - 3x + 1",
        r"\sqrt{x^{2} + 1}",
        r"\overline{AB} = 3",
        r"\lim_{x \to 0} \frac{f(x)}{x}",
        r"\int_{0}^{2} f(x)\,dx",
        r"\left( x - 1 \right)^{2}",
        r"\left\{ x \mid x > 0 \right\}",
        r"f(x) = \begin{cases} x^2 & (x \geq 0) \\ -x^2 & (x < 0) \end{cases}",
    ]
    for s in samples:
        print('IN :', s)
        try:
            print('OUT:', latex_to_hwp_eq(s))
        except Exception as e:
            print('ERROR:', e)
        print()
