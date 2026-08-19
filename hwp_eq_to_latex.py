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

KEYWORDS = ['LEFT', 'RIGHT', 'left', 'right', 'sqrt', 'bar', 'rm', 'it',
            'over', 'dsty', 'tsty'] + list(SYMBOL_MAP.keys())
KEYWORD_PATTERN = r'\b(?:' + '|'.join(sorted(KEYWORDS, key=len, reverse=True)) + r')\b'

TOKEN_REGEX = re.compile(
    KEYWORD_PATTERN + r'|[{}()^_]|`|[A-Za-z]+|[0-9]+(?:\.[0-9]+)?|\S'
)

def tokenize(script: str):
    return [t for t in TOKEN_REGEX.findall(script)]


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

    def strip_braces(self, s: str) -> str:
        s = s.strip()
        if s.startswith('{') and s.endswith('}'):
            return s[1:-1]
        return s

    def parse_sequence(self, stop_tokens):
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

        return ' '.join(a for a in atoms if a != '')

    def parse_atom(self):
        t = self.peek()

        if t == '{':
            self.next()
            inner = self.parse_sequence({'}'})
            self.expect('}')
            return '{' + inner + '}'

        if t == 'sqrt':
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
                # 중괄호 없는 형태: rm AB it  (다음 'it'/경계 전까지가 로만체 내용)
                parts = []
                while self.peek() not in ('it', '}', 'RIGHT', 'right', None):
                    parts.append(self.next())
                inner = ''.join(parts)
            if self.peek() == 'it':
                self.next()
            # rm{ bar AB } 처럼 내부가 이미 \bar{...}로 변환된 경우 -> \overline로 통일
            m = re.match(r'\\bar\{(.+?)\}\s*$', inner.strip())
            if m:
                return r'\overline{' + m.group(1) + '}'
            return r'\mathrm{' + inner + '}'

        if t in ('LEFT', 'left'):
            self.next()
            open_delim = self.next()
            inner = self.parse_sequence({'RIGHT', 'right'})
            self.next()
            close_delim = self.next() or ')'
            return r'\left' + str(open_delim) + inner + r'\right' + str(close_delim)

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
