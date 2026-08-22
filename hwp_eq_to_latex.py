"""
HWP 수식 스크립트(DSL) -> LaTeX 변환기 프로토타입 v2
- ^, _, over 처리를 parse_sequence() 하나로 통일 (그룹/괄호 내부에서도 동일하게 동작)
"""
import re

SYMBOL_MAP = {
    'times': r'\times', 'div': r'\div',
    'therefore': r'\therefore', 'because': r'\because',
    'cdots': r'\cdots', 'ldots': r'\ldots', 'vdots': r'\vdots', 'ddots': r'\ddots',
    'cap': r'\cap', 'cup': r'\cup', 'in': r'\in', 'notin': r'\notin',
    'subset': r'\subset', 'supset': r'\supset',
    'le': r'\le', 'ge': r'\ge', 'ne': r'\ne',
    'lt': '<', 'gt': '>',
    'pm': r'\pm', 'mp': r'\mp',
    'infty': r'\infty',
    'alpha': r'\alpha', 'beta': r'\beta', 'gamma': r'\gamma', 'theta': r'\theta',
    'pi': r'\pi', 'phi': r'\phi', 'omega': r'\omega', 'delta': r'\delta',
    'sum': r'\sum', 'prod': r'\prod', 'int': r'\int', 'lim': r'\lim',
    'to': r'\to', 'rightarrow': r'\rightarrow', 'leftarrow': r'\leftarrow',
    'partial': r'\partial', 'nabla': r'\nabla',
    'angle': r'\angle', 'perp': r'\perp', 'parallel': r'\parallel',
    'sim': r'\sim', 'approx': r'\approx', 'equiv': r'\equiv',
    'circ': r'\circ',
    'ANGLE': r'\angle', 'DEG': r'^\circ',
}

KEYWORDS = ['LEFT', 'RIGHT', 'left', 'right', 'sqrt', 'root', 'bar', 'rm', 'it',
            'over', 'dsty', 'tsty', 'matrix', 'pile'] + list(SYMBOL_MAP.keys())
KEYWORD_PATTERN = r'\b(?:' + '|'.join(sorted(KEYWORDS, key=len, reverse=True)) + r')\b'

TOKEN_REGEX = re.compile(
    KEYWORD_PATTERN + r'|[{}()^_#&]|`|[A-Za-z]+|[0-9]+(?:\.[0-9]+)?|\S'
)

def _split_repeated_keyword(word: str):
    """공백 없이 같은 키워드가 반복 붙은 토큰(예: 'cdotscdots')을 쪼갠다.
    길이 3 미만 키워드(in, to, pi, le 등)는 평범한 변수명과 겹칠 수 있어 제외."""
    for kw in SYMBOL_MAP:
        if len(kw) < 3 or len(word) <= len(kw) or len(word) % len(kw) != 0:
            continue
        if word == kw * (len(word) // len(kw)):
            return [kw] * (len(word) // len(kw))
    return None


def tokenize(script: str):
    tokens = []
    for t in TOKEN_REGEX.findall(script):
        if t not in KEYWORDS and re.fullmatch(r'[A-Za-z]+', t):
            split = _split_repeated_keyword(t)
            if split:
                tokens.extend(split)
                continue
        tokens.append(t)
    return tokens


class Parser:
    def __init__(self, tokens):
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
        return t

    _DELIM_ESCAPE = {'{': r'\{', '}': r'\}'}

    def _latex_delim(self, tok) -> str:
        # LEFT/RIGHT 구분자로 '{'/'}' 가 오면 LaTeX에서 이스케이프해야 한다
        # (\left{ 는 문법 오류, \left\{ 가 맞다).
        return self._DELIM_ESCAPE.get(tok, str(tok))

    def strip_braces(self, s: str) -> str:
        s = s.strip()
        if s.startswith('{') and s.endswith('}'):
            return s[1:-1]
        return s

    def parse_sequence(self, stop_tokens, sep=' '):
        atoms = []
        while self.peek() is not None and self.peek() not in stop_tokens:
            t = self.peek()

            if t == '^':
                self.next()
                sup = self.parse_atom()
                if atoms:
                    atoms[-1] = atoms[-1] + '^{' + self.strip_braces(sup) + '}'
                else:
                    atoms.append('^{' + self.strip_braces(sup) + '}')
                continue

            if t == '_':
                self.next()
                sub = self.parse_atom()
                if atoms:
                    atoms[-1] = atoms[-1] + '_{' + self.strip_braces(sub) + '}'
                else:
                    atoms.append('_{' + self.strip_braces(sub) + '}')
                continue

            if t == 'over':
                self.next()
                denom = self.parse_atom()
                numer = atoms.pop() if atoms else ''
                atoms.append(r'\frac{' + self.strip_braces(numer) + '}{' + self.strip_braces(denom) + '}')
                continue

            atoms.append(self.parse_atom())

        return sep.join(a for a in atoms if a != '')

    def parse_matrix_rows(self, split_columns: bool):
        """matrix{}/pile{} 내부를 '#'(행 구분)과, matrix의 경우 '&'(열 구분) 기준으로 나눈다."""
        rows = []
        while True:
            if split_columns:
                cells = [self.parse_sequence({'&', '#', '}'})]
                while self.peek() == '&':
                    self.next()
                    cells.append(self.parse_sequence({'&', '#', '}'}))
                rows.append(cells)
            else:
                rows.append([self.parse_sequence({'#', '}'})])
            if self.peek() == '#':
                self.next()
                continue
            break
        return rows

    def parse_atom(self):
        t = self.peek()

        if t == '{':
            self.next()
            inner = self.parse_sequence({'}'})
            self.expect('}')
            return '{' + inner + '}'

        if t in ('sqrt', 'root'):
            self.next()
            if self.peek() == '{':
                self.next()
                inner = self.parse_sequence({'}'})
                self.expect('}')
            else:
                inner = self.parse_atom()  # 중괄호 없는 단일 인자 (예: sqrt2, sqrt10)
            return r'\sqrt{' + inner + '}'

        if t == 'bar':
            self.next()
            if self.peek() == '{':
                self.next()
                inner = self.parse_sequence({'}'})
                self.expect('}')
            else:
                inner = self.parse_atom()  # 중괄호 없는 단일 인자
            m = re.match(r'\\mathrm\{(.+?)\}\s*$', inner.strip())
            if m:
                return r'\overline{' + m.group(1) + '}'
            return r'\bar{' + inner + '}'

        if t == 'rm':
            self.next()
            if self.peek() == '{':
                self.next()
                inner = self.parse_sequence({'}'})
                self.expect('}')
            else:
                # 중괄호 없는 형태: rm AB it / rm bar{AB}  (다음 'it'/경계 전까지가
                # 로만체 내용). parse_sequence()로 파싱해야 안의 bar/^/_ 같은
                # 구성도 제대로 처리된다(raw 토큰을 그냥 이어붙이면 안 됨).
                # sep=''인 이유: 로만체 텍스트는 원래 붙여 써야 한다(AB, m 등).
                inner = self.parse_sequence({'it', '}', 'RIGHT', 'right'}, sep='')
            if self.peek() == 'it':
                self.next()
            # rm{ bar AB } 처럼 내부가 이미 \bar{...}로 변환된 경우 -> \overline로 통일
            m = re.match(r'\\bar\{(.+?)\}\s*$', inner.strip())
            if m:
                return r'\overline{' + m.group(1) + '}'
            return r'\mathrm{' + inner + '}'

        if t in ('matrix', 'pile'):
            is_matrix = (t == 'matrix')
            self.next()
            self.expect('{')
            rows = self.parse_matrix_rows(split_columns=is_matrix)
            self.expect('}')
            latex_rows = [' & '.join(cells) for cells in rows]
            body = r' \\ '.join(latex_rows)
            return r'\begin{matrix}' + body + r'\end{matrix}'

        if t in ('LEFT', 'left'):
            self.next()
            open_delim = self._latex_delim(self.next())
            inner = self.parse_sequence({'RIGHT', 'right'})
            self.next()
            close_delim = self._latex_delim(self.next() or ')')
            return r'\left' + open_delim + inner + r'\right' + close_delim

        if t == '`':
            self.next()
            return r'\,'

        if t in SYMBOL_MAP:
            self.next()
            return SYMBOL_MAP[t]

        if t in ('dsty', 'tsty', 'it'):
            self.next()
            return ''

        if t in ('(', ')'):
            self.next()
            return t

        self.next()
        return t


def hwp_eq_to_latex(script: str) -> str:
    tokens = tokenize(script)
    p = Parser(tokens)
    return p.parse_sequence(set())


if __name__ == '__main__':
    samples = [
        "t ^{2} le{17} over {2}",
        "= sqrt{ left(2-t right)^{2}+ left(t- left(-2 right) right)^{2}}",
        "{ bar{rm{AB}it}}",
        "= LEFT ( 1-2t RIGHT ) ^{2} + LEFT ( -4t-3 RIGHT ) ^{2}",
        "rmQ LEFT ( 0,`` {10} over{3} RIGHT )",
        "therefore~ k=1",
        "{rm{A}it} left(t,``-2 right)`",
    ]
    for s in samples:
        print('IN :', s)
        try:
            print('OUT:', hwp_eq_to_latex(s))
        except Exception as e:
            print('ERROR:', e)
        print()
