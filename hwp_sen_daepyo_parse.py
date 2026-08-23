"""
쎈수학 "대표문제" HWP 자료(소단원별 1개 파일)에서 유형 번호/이름과
대표문제 번호, 그 정답까지 뽑는다.

이 파일들은 한 소단원 안에서 두 부분으로 구성된다:
  1. "[유형 NN]제목" 다음에 그 유형의 "대표문제" 번호(4자리)와 문제 본문이
     이어지는 목록 - 유형이 바뀔 때마다 새 "[유형 NN]"이 나온다.
  2. 문서 뒷부분에 같은 소단원명이 다시 나오면서, 문제번호+정답 쌍이
     쭉 나열되는 정답표.
문제 본문(수식 포함)은 다루지 않는다 - 필요한 건 "이 대표문제 번호가
어느 유형인지"와 "그 정답이 뭔지"뿐이다. 대표문제가 아닌 문제(그 유형에
속하지만 대표문제 뒤에 이어지는 일반 문제들)의 번호는 이 자료에 없다 -
"현재 유형의 대표문제 번호 <= 문제번호 < 다음 유형의 대표문제 번호"로
범위 매칭해서 유형을 추정해야 한다(이 파일에서는 매핑 자체만 만든다).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from hwp_eq_to_latex import hwp_eq_to_latex
from hwp_workbook_parse import _xml_root, extract_equation_scripts

_PROBLEM_NUM_RE = re.compile(r'^\d{4}$')
# 정답으로 인정할 조각: 원문자(①~⑤) 또는 수식($...$)이 하나라도 있어야 한다.
# 합답형(예: "① 또는 ④") 문제 중 일부는 원문자 글자 자체가 텍스트로
# 추출되지 않아 ", " / " 또는 " 같은 연결어 조각만 남는 경우가 있는데,
# 이런 건 정답이 아니라 자료 자체의 누락이므로 None으로 남겨야 한다.
_VALID_ANSWER_RE = re.compile(r'[①②③④⑤]|^\$')


@dataclass
class RepresentativeType:
    type_no: str
    title: str
    problem_no: str
    answer: str | None = None


def _text_stream(path: str) -> list[str]:
    """Text/EqEdit을 문서 순서대로 훑어 하나의 조각 목록으로 합친다.

    단답형(서술형) 문제는 정답표에 답이 원문자가 아니라 수식(EqEdit)으로
    적혀 있어서, Text만 보면 정답 자리가 통째로 비어 보인다.
    """
    root = _xml_root(path)
    equations = iter(extract_equation_scripts(path))

    def next_latex() -> str:
        script = next(equations, None)
        if script is None:
            return ''
        try:
            return hwp_eq_to_latex(script)
        except Exception:
            return script

    parts: list[str] = []
    for el in root.iter():
        if el.tag == 'Text' and el.text:
            parts.append(el.text)
        elif el.tag == 'EqEdit':
            latex = next_latex()
            if latex:
                parts.append(f'${latex}$')
    return parts


def extract_representative_types(path: str) -> list[RepresentativeType]:
    return _parse_texts(_text_stream(path))


def _parse_texts(texts: list[str]) -> list[RepresentativeType]:
    entries: list[RepresentativeType] = []
    i = 0
    n = len(texts)

    # 1단계: "[유형 NN]제목\nNNNN" 목록을 훑는다.
    while i < n:
        if texts[i].strip() == '[' and i + 1 < n and texts[i + 1].strip().startswith('유형'):
            type_no = texts[i + 2].strip() if i + 2 < n else ''
            j = i + 4  # '[', '유형 ', 'NN', ']' 다음부터
            title_parts = []
            while j < n and not _PROBLEM_NUM_RE.match(texts[j].strip()):
                title_parts.append(texts[j])
                j += 1
            if j < n:
                problem_no = texts[j].strip()
                entries.append(RepresentativeType(
                    type_no=type_no, title=''.join(title_parts).strip(), problem_no=problem_no,
                ))
                i = j + 1
                continue
        i += 1

    # 2단계: 정답표("NNNN 정답기호"). 같은 번호가 문서에 두 번 나온다
    # (1단계 목록에 한 번, 뒤쪽 정답표에 한 번) - 마지막 등장 위치를
    # 정답표로 보고 그 다음 조각을 정답으로 삼는다.
    for e in entries:
        positions = [k for k, t in enumerate(texts) if t.strip() == e.problem_no]
        if len(positions) < 2:
            continue
        idx = positions[-1]
        if idx + 1 < n:
            nxt = texts[idx + 1].strip()
            if nxt and not _PROBLEM_NUM_RE.match(nxt) and _VALID_ANSWER_RE.search(nxt):
                e.answer = nxt

    return entries


if __name__ == '__main__':
    import sys
    for p in sys.argv[1:]:
        print(f'=== {p} ===')
        for e in extract_representative_types(p):
            print(f'  [유형 {e.type_no}] {e.title}  (대표문제 {e.problem_no}, 정답 {e.answer})')
