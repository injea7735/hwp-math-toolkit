"""
"내신고쟁이" 계열 "정답과 풀이" PDF에서 문제 번호별 정답만 뽑는다.

plain-text 추출(page.get_text())로 보면 이 해설 PDF는 한 줄에 3자리
문제번호만 있는 줄("001" 처럼 공백 포함해서 그 줄에 번호 말고 아무것도
없음) 다음 줄에 들여쓴 정답이 오고, 그 다음부터 다음 문제 번호가 나올
때까지 풀이 설명이 이어지는 아주 규칙적인 구조다. 좌표 기반으로 "번호와
같은 줄의 오른쪽 텍스트"를 모으는 방식은 페이지 안의 다른 박스(TIP,
참고 등)까지 같이 걸려 들어와서 지저분해져 이 방식으로 바꿨다.

문제 번호는 책 전체를 통틀어 이어지므로(대단원마다 리셋되지 않음) 대단원
추적 없이 번호 문자열만으로 매칭할 수 있다. 풀이 설명 텍스트는 다루지
않는다 - 정답 한 줄만 읽는다.
"""
from __future__ import annotations

import re

import fitz

# 번호만 있는 줄 뒤에 백스페이스(\x08) 같은 제어문자가 붙어 나오는 경우가
# 있어(폰트 커닝 힌트로 추정) 순수 공백뿐 아니라 제어문자까지 걷어낸다.
_NUMBER_LINE = re.compile(r'^\d{3}[\s\x00-\x1f]*$')

# 정답 줄 맨 앞에 "정답" 라벨 아이콘(비표준 폰트의 PUA 코드포인트) 이
# 공백과 함께 붙어 나오는 경우가 있어 걷어낸다.
_PUA_RANGE = (0xE000, 0xF8FF)


def _strip_leading_noise(text: str) -> str:
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace() or _PUA_RANGE[0] <= ord(ch) <= _PUA_RANGE[1]:
            i += 1
            continue
        break
    return text[i:]


def extract_answers(pdf_path: str) -> dict[str, str]:
    doc = fitz.open(pdf_path)
    answers: dict[str, str] = {}

    for pno in range(doc.page_count):
        lines = doc[pno].get_text().split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not _NUMBER_LINE.match(stripped):
                continue
            number = stripped[:3]

            # 번호 다음 줄이 그 문제의 정답이다(들여쓰기만 있고 비어 있는
            # 줄은 건너뛰고 실제 내용이 있는 첫 줄을 찾는다).
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                continue

            answer = _strip_leading_noise(lines[j]).strip()
            if answer:
                answers[number] = answer

    doc.close()
    return answers


if __name__ == '__main__':
    import sys
    path = sys.argv[1]
    result = extract_answers(path)
    print('추출된 정답 수:', len(result))
