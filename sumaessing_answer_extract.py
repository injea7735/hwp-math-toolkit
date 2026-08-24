"""
"수매씽" 해설 PDF에서 문제 번호별 정답만 뽑는다.

이 해설 PDF는 "내신고쟁이" 해설들과 달리 번호와 정답이 같은 줄에 바로
붙어 나온다("0121  ③" 처럼) - 번호 다음 줄이 정답인 패턴이 아니라 한
줄짜리 정규식으로 바로 끝난다.
"""
from __future__ import annotations

import re

import fitz

_NUMBER_ANSWER_LINE = re.compile(r'^(\d{4})\s+(.+)$')


def extract_answers(pdf_path: str) -> dict[str, str]:
    doc = fitz.open(pdf_path)
    answers: dict[str, str] = {}

    for pno in range(doc.page_count):
        for line in doc[pno].get_text().split('\n'):
            m = _NUMBER_ANSWER_LINE.match(line.strip())
            if m:
                answers[m.group(1)] = m.group(2).strip()

    doc.close()
    return answers


if __name__ == '__main__':
    import sys
    path = sys.argv[1]
    result = extract_answers(path)
    print('추출된 정답 수:', len(result))
