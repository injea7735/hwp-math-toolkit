"""
HWP 수식 스크립트(DSL) -> LaTeX 변환기 프로토타입 v2
- ^, _, over 처리를 parse_sequence() 하나로 통일 (그룹/괄호 내부에서도 동일하게 동작)
"""
import re

SYMBOL_MAP = {
    'times': r'\times', 'div': r'\div',
    'therefore': r'\therefore', 'because': r'\because',
    'cdots': r'\cdots', 'ldots': r'\ldots', 'vdots': r'\vdots', 'ddots': r'\ddots',
    'cap': r'\cap', 'cup': r'\cup', 'in': r'\in', 'notin': r'\notin', 'not': r'\not',
    'smallinter': r'\cap', 'smallunion': r'\cup',
    'subset': r'\subset', 'supset': r'\supset',
    'le': r'\le', 'ge': r'\ge', 'ne': r'\ne', 'leq': r'\le', 'geq': r'\ge',
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
    'circ': r'\circ', 'ast': r'\ast', 'triangle': r'\triangle',
    'underbrace': r'\underbrace', 'emptyset': r'\emptyset',
    'ANGLE': r'\angle', 'DEG': r'^\circ',
}

KEYWORDS = ['LEFT', 'RIGHT', 'left', 'right', 'sqrt', 'root', 'bar', 'rm', 'it',
            'over', 'dsty', 'tsty', 'matrix', 'pile'] + list(SYMBOL_MAP.keys())
KEYWORD_PATTERN = r'\b(?:' + '|'.join(sorted(KEYWORDS, key=len, reverse=True)) + r')\b'

TOKEN_REGEX = re.compile(
    KEYWORD_PATTERN + r'|[{}()^_#&]|`|[A-Za-z]+|[0-9]+(?:\.[0-9]+)?|\S'
)

# HWP 수식 편집기는 명령어를 대문자로 써도(CUP, RM, OVER ...) 그대로 받아들인다.
# 다만 in/to/pi/le/ge 같은 2글자짜리는 실제 대문자 변수명(점 이름 두 개를
# 붙인 선분명 등: PI, TO ...)과 겹칠 위험이 커서 일반 규칙에서 제외하고,
# 데이터에서 실제로 대문자로 쓰이는 게 확인된 것만 예외로 허용한다.
_CASE_INSENSITIVE_MIN_LEN = 3
_CASE_INSENSITIVE_SHORT_EXCEPTIONS = {'rm', 'it', 'in'}
_KEYWORD_SET = set(KEYWORDS)


def _canonical_keyword(word: str):
    """대문자로 쓰인 키워드(CUP 등)를 표준 소문자 토큰으로 되돌린다.
    이미 KEYWORDS에 있는 토큰(LEFT 등 원래부터 대소문자 둘 다 등록된 것)이나
    이미 소문자인 토큰은 건드리지 않는다."""
    if word in _KEYWORD_SET:
        return None
    lower = word.lower()
    if lower == word or lower not in _KEYWORD_SET:
        return None
    if lower in _CASE_INSENSITIVE_SHORT_EXCEPTIONS or len(word) >= _CASE_INSENSITIVE_MIN_LEN:
        return lower
    return None


_LOWER_KEYWORDS = sorted({k.lower() for k in KEYWORDS}, key=len, reverse=True)


def _decompose_alpha_token(word: str, _depth: int = 0):
    """공백 없이 붙어버린 순수 알파벳 토큰을 [키워드/변수, ...] 로 쪼갠다.
    실제 자료에서 확인된 세 가지 패턴을 하나로 처리한다:
      - 키워드 반복: 'cdotscdots' -> ['cdots', 'cdots']
      - 키워드+변수: 'smallunionB', 'barAB' -> ['smallunion', 'B'] / ['bar', 'AB']
      - 키워드+키워드: 'TIMESBAR' -> ['times', 'bar']
    앞에서부터 가장 긴 키워드를 접두어로 찾고, 나머지를 재귀적으로 다시
    분해해본다. 못 찾으면 나머지를 대문자로 시작하는 1~3글자 변수로만
    허용한다. 짧은(3글자 미만) 키워드는 실제 변수명과 겹칠 위험이 커서
    rm/it 처럼 데이터에서 확인된 것만 예외로 허용한다."""
    if _depth > 5 or not word:
        return None
    lower = word.lower()
    for kw in _LOWER_KEYWORDS:
        if len(kw) < 3 and kw not in _CASE_INSENSITIVE_SHORT_EXCEPTIONS:
            continue
        if not lower.startswith(kw):
            continue
        rest = word[len(kw):]
        if not rest:
            return [kw]
        sub = _decompose_alpha_token(rest, _depth + 1)
        if sub is not None:
            return [kw] + sub
        if 1 <= len(rest) <= 3 and rest[0].isupper():
            return [kw, rest]
    return None


def tokenize(script: str):
    tokens = []
    for t in TOKEN_REGEX.findall(script):
        if t not in KEYWORDS and re.fullmatch(r'[A-Za-z]+', t):
            canonical = _canonical_keyword(t)
            if canonical:
                tokens.append(canonical)
                continue
            split = _decompose_alpha_token(t)
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
        if t is None and tok == '}':
            # HWP 수식 편집기는 커서를 밖으로 옮기면 마지막 '}' 를 입력하지
            # 않아도 그냥 저장한다(스크립트 맨 끝에서만 나타남) -> 암묵적으로
            # 닫힌 것으로 보고 넘어간다. 중간에 다른 토큰이 나오는 진짜 구조
            # 오류는 여전히 에러로 처리한다.
            return tok
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
