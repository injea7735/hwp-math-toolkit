"""공통수학1/2 "내신고쟁이" 해설 PDF에서 풀이를 뽑아 HWP에서 이미 들어간
Problem 행에 채운다.

이 해설 PDF는 pdf_answer_extract.py가 다루는 "내신고쟁이" 계열과 똑같은
포맷(3자리 번호 줄 -> 정답 -> 다음 번호 전까지 풀이)이지만, 번호가 소단원
파일별로 리셋되지 않고 **책 전체를 통틀어 이어진다** - 그래서 소단원 HWP
파일에서 다시 뽑은 문제 목록(문서 순서)에 "이 소단원이 책에서 몇 번째
문제부터 시작하는지"(START_OFFSET)를 더해서 전역 번호를 계산해야 매칭된다.

START_OFFSET은 추측이 아니라 실제로 확인한 값이다: 각 소단원 경계
페이지에 정말로 나오는 문제 번호를 직접 읽어서 대조했다(예: 공통수학1
"순열과 조합" 경계 페이지에 정말로 "684"가 나오고, 공통수학1 파일들의
문제 수를 누적한 값도 정확히 684 - 두 방법이 서로 일치함을 확인).

**중요**: 공통수학1은 파일명이 암시하는 순서("...09행렬" 다음
"...09순열과조합")와 실제 책 순서가 다르다(순열과 조합이 행렬보다 먼저
나온다) - 이것도 페이지에 실제로 나오는 번호로 확인했다. 아래
COMMON_MATH_1 순서는 파일명이 아니라 이 확인된 실제 책 순서를 따른다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from hwp_workbook_parse import extract_outline, extract_problems
from pdf_answer_extract import extract_explanations
from import_workbook_problems import split_choices
from models import Problem, ProblemType, init_db

_GONGTONG1_DIR = (
    r'N:\공유\공유받은\#[자료] 개정수학 모음 ★\#01 공통수학1\[공수1] 02 유형서'
    r'\[유형서] 공통수학1 내신 고쟁이][공통수학1] 한글 ★'
)
_GONGTONG2_DIR = (
    r'N:\공유\공유받은\#[자료] 개정수학 모음 ★\#02 공통수학2\[공수2] 02 유형서'
    r'\[유형서] 공통수학2 내신고쟁이 [한글]★★'
)

# (subject, hwp 경로, unit_title_override, 이 책에서 이 소단원이 시작하는
# 전역 문제 번호) - 실제 책 순서대로, 페이지 대조로 확인됨.
FILES_WITH_OFFSET: list[tuple[str, str, str | None, int]] = [
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]01다항식의연산.hwp', None, 1),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]02항등식과나머지정리.hwp', None, 78),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]03인수분해.hwp', None, 162),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]04복소수와이차방정식.hwp', None, 229),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]05이차방정식과이차함수.hwp', None, 374),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]06여러가지방정식.hwp', None, 463),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]07여러가지부등식.hwp', None, 539),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]08경우의수.hwp', None, 615),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]09순열과조합.hwp', None, 684),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]09행렬.hwp', '행렬', 767),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]01평면좌표.hwp', None, 1),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]02직선의방정식.hwp', None, 54),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]03원의방정식.hwp', None, 123),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]04도형의이동.hwp', None, 201),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]05집합.hwp', None, 262),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]06명제.hwp', None, 368),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]07함수.hwp', None, 477),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]08유리함수와무리함수.hwp', None, 609),
]

HAESEOL_PDF = {
    '공통수학1': fr'{_GONGTONG1_DIR}\유형내신 고쟁이 공통수학1 (22개정) - 해설.pdf',
    '공통수학2': fr'{_GONGTONG2_DIR}\유형내신 고쟁이 공통수학2 (22개정) - 해설.pdf',
}


def backfill(session: Session, apply: bool) -> dict:
    explanations_by_subject = {
        subject: extract_explanations(path) for subject, path in HAESEOL_PDF.items()
    }

    stats = {"matched": 0, "no_type": 0, "no_match": 0, "no_explanation": 0, "changed": 0}
    type_cache: dict[str, ProblemType | None] = {}

    for subject, path, unit_title_override, start in FILES_WITH_OFFSET:
        outline = extract_outline(path)
        unit_title = unit_title_override or outline.unit_title
        if not unit_title:
            continue
        explanations = explanations_by_subject[subject]

        for i, p in enumerate(extract_problems(path)):
            global_no = start + i
            explanation = explanations.get(f'{global_no:03d}')
            if explanation is None:
                stats["no_explanation"] += 1
                continue

            code = f'{subject}-{unit_title}-{p.type_no}'
            if code not in type_cache:
                type_cache[code] = session.query(ProblemType).filter_by(code=code).one_or_none()
            ptype = type_cache[code]
            if ptype is None:
                stats["no_type"] += 1
                continue

            body, _ = split_choices(p.stem)
            row = (
                session.query(Problem)
                .filter_by(problem_type_id=ptype.id, stem_latex=body)
                .one_or_none()
            )
            if row is None:
                stats["no_match"] += 1
                continue

            stats["matched"] += 1
            if row.explanation != explanation:
                stats["changed"] += 1
                if apply:
                    row.explanation = explanation

    if apply:
        session.commit()
    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    engine = init_db()
    with Session(engine) as session:
        result = backfill(session, args.apply)
    mode = '적용됨' if args.apply else '드라이런(DB 미변경)'
    print(f'[{mode}] {result}')


if __name__ == '__main__':
    main()
