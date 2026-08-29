"""공통수학1/2 "내신고쟁이" HWP 유형서에서 STEP 난이도(STEP1 교과서를
정복하는 핵심 유형 / STEP2 실전 유형 / STEP3 최고난도 유형)를 읽어
기존 DB Problem 행에 difficulty_tier를 채운다.

STEP1만 채운다 - 지금 DB에 들어있는 545개 행은 전부 STEP1이다. 확인된
사실: hwp_workbook_parse.extract_problems()의 기존 종료 조건("유형 제목이
반복되면 정답 섹션 시작으로 보고 멈춘다")이 STEP1->STEP2 경계에서 항상
잘못 발동한다 - 각 STEP 섹션이 같은 유형 제목(01, 02, ...)을 그대로
재사용하기 때문에, STEP2 섹션의 첫 유형 제목이 "반복"으로 오인되어 거기서
멈춘다. 그래서 import_workbook_problems.py로 이미 들어간 545개 행은 전부
실제로 STEP1 구간의 문제였다(11개 파일 직접 추출해서 100% STEP1임을
확인함). STEP2/STEP3 문제 자체는 지금 DB에 아예 없다 - 이건 별도의
추출 버그 수정 + 재추출 작업이 필요하고, 이 스크립트의 범위가 아니다.

각 문제는 import_workbook_problems.insert_problems()가 썼던 것과 똑같은
매칭 키((problem_type_id, stem_latex=split_choices 적용 후 본문))로
기존 행을 찾아 매칭한다 - 추측이 아니라 원본을 다시 파싱해서 정확히
같은 문제인지 확인 후 채운다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from hwp_workbook_parse import extract_outline, extract_problems
from import_workbook_problems import split_choices
from models import DifficultyTier, Problem, ProblemType, init_db

# (subject, hwp 파일 경로) 목록 - import_workbook_problems.py로 이미 임포트된
# 것과 동일한 20개 소단원 파일.
_GONGTONG1_DIR = (
    r'N:\공유\공유받은\#[자료] 개정수학 모음 ★\#01 공통수학1\[공수1] 02 유형서'
    r'\[유형서] 공통수학1 내신 고쟁이][공통수학1] 한글 ★'
)
_GONGTONG2_DIR = (
    r'N:\공유\공유받은\#[자료] 개정수학 모음 ★\#02 공통수학2\[공수2] 02 유형서'
    r'\[유형서] 공통수학2 내신고쟁이 [한글]★★'
)

FILES: list[tuple[str, str]] = [
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]01다항식의연산.hwp'),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]02항등식과나머지정리.hwp'),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]03인수분해.hwp'),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]04복소수와이차방정식.hwp'),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]05이차방정식과이차함수.hwp'),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]06여러가지방정식.hwp'),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]07여러가지부등식.hwp'),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]08경우의수.hwp'),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]09행렬.hwp'),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]09순열과조합.hwp'),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]01평면좌표.hwp'),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]02직선의방정식.hwp'),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]03원의방정식.hwp'),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]04도형의이동.hwp'),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]05집합.hwp'),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]06명제.hwp'),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]07함수.hwp'),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]08유리함수와무리함수.hwp'),
]

_TIER_NAME_BY_STEP = {'STEP1': '핵심 유형'}


def backfill(session: Session, apply: bool) -> dict:
    tier = session.query(DifficultyTier).filter_by(name='핵심 유형').one()

    stats = {'matched': 0, 'no_type': 0, 'no_match': 0, 'other_tier': 0, 'changed': 0}
    type_cache: dict[str, ProblemType | None] = {}

    for subject, path in FILES:
        outline = extract_outline(path)
        unit_title = outline.unit_title
        if not unit_title:
            continue
        for p in extract_problems(path):
            tier_name = _TIER_NAME_BY_STEP.get(p.tier)
            if tier_name is None:
                stats['other_tier'] += 1
                continue

            code = f'{subject}-{unit_title}-{p.type_no}'
            if code not in type_cache:
                type_cache[code] = session.query(ProblemType).filter_by(code=code).one_or_none()
            ptype = type_cache[code]
            if ptype is None:
                stats['no_type'] += 1
                continue

            body, _ = split_choices(p.stem)
            row = (
                session.query(Problem)
                .filter_by(problem_type_id=ptype.id, stem_latex=body)
                .one_or_none()
            )
            if row is None:
                stats['no_match'] += 1
                continue

            stats['matched'] += 1
            if row.difficulty_tier_id != tier.id:
                stats['changed'] += 1
                if apply:
                    row.difficulty_tier_id = tier.id

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
