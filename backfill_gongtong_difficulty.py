"""공통수학1/2 "내신고쟁이" HWP 유형서에서 STEP 난이도(STEP1 교과서를
정복하는 핵심 유형 / STEP2 실전 유형 / STEP3 최고난도 유형)를 읽어
DB Problem 행에 difficulty_tier를 채운다.

STEP1은 기존 DifficultyTier "핵심 유형"(다른 책들도 쓰는 이름)에, STEP3는
"최고난도 유형"에 매칭한다 - 둘 다 이름이 원본 배너 문구와 정확히 같다.
STEP2는 원본 배너 문구가 "실전 유형"으로, 기존 "심화 유형"과 이름이 달라
새 tier로 만든다(내용이 비슷하다고 이름을 억지로 합치지 않는다).

각 문제는 import_workbook_problems.insert_problems()가 썼던 것과 똑같은
매칭 키((problem_type_id, stem_latex=split_choices 적용 후 본문))로
기존 행을 찾아 매칭한다 - 추측이 아니라 원본을 다시 파싱해서 정확히
같은 문제인지 확인 후 채운다.

주의: "09행렬.hwp"는 파일 내부 단원 라벨이 "경우의 수"로 잘못 박혀 있다
(원본 파일 자체의 복사-붙여넣기 흔적 - import_workbook_outline.py에서도
이미 알려진 이슈). extract_outline()이 반환하는 unit_title을 그대로 쓰면
이 파일의 문제가 전혀 다른 단원("경우의 수")의 유형에 잘못 매칭된다 -
실제로 한 번 이렇게 잘못 삽입했다가 발견하고 삭제+재삽입으로 복구한 적
있음. 그래서 FILES에 세 번째 값(unit_title_override)을 둔다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from hwp_workbook_parse import extract_outline, extract_problems
from import_workbook_problems import split_choices
from models import DifficultyTier, Problem, ProblemType, init_db

# (subject, hwp 파일 경로, unit_title_override) 목록 - import_workbook_problems.py로
# 이미 임포트된 것과 동일한 18개 소단원 파일. override는 09행렬.hwp에만 필요.
_GONGTONG1_DIR = (
    r'N:\공유\공유받은\#[자료] 개정수학 모음 ★\#01 공통수학1\[공수1] 02 유형서'
    r'\[유형서] 공통수학1 내신 고쟁이][공통수학1] 한글 ★'
)
_GONGTONG2_DIR = (
    r'N:\공유\공유받은\#[자료] 개정수학 모음 ★\#02 공통수학2\[공수2] 02 유형서'
    r'\[유형서] 공통수학2 내신고쟁이 [한글]★★'
)

FILES: list[tuple[str, str, str | None]] = [
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]01다항식의연산.hwp', None),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]02항등식과나머지정리.hwp', None),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]03인수분해.hwp', None),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]04복소수와이차방정식.hwp', None),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]05이차방정식과이차함수.hwp', None),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]06여러가지방정식.hwp', None),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]07여러가지부등식.hwp', None),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]08경우의수.hwp', None),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]09행렬.hwp', '행렬'),
    ('공통수학1', fr'{_GONGTONG1_DIR}\[2025내신고쟁이][공통수학Ⅰ]09순열과조합.hwp', None),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]01평면좌표.hwp', None),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]02직선의방정식.hwp', None),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]03원의방정식.hwp', None),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]04도형의이동.hwp', None),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]05집합.hwp', None),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]06명제.hwp', None),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]07함수.hwp', None),
    ('공통수학2', fr'{_GONGTONG2_DIR}\[2025유형내신고쟁이][공통수학Ⅱ]08유리함수와무리함수.hwp', None),
]

_TIER_NAME_BY_STEP = {'STEP1': '핵심 유형', 'STEP2': '실전 유형', 'STEP3': '최고난도 유형'}


def _get_or_create_tier(session: Session, name: str, order: int) -> DifficultyTier:
    tier = session.query(DifficultyTier).filter_by(name=name).one_or_none()
    if tier is None:
        tier = DifficultyTier(name=name, order=order)
        session.add(tier)
        session.flush()
    return tier


def backfill(session: Session, apply: bool) -> dict:
    tiers = {
        'STEP1': _get_or_create_tier(session, '핵심 유형', 1),
        'STEP2': _get_or_create_tier(session, '실전 유형', 2),
        'STEP3': _get_or_create_tier(session, '최고난도 유형', 3),
    }

    stats = {'matched': 0, 'no_type': 0, 'no_match': 0, 'other_tier': 0, 'changed': 0}
    type_cache: dict[str, ProblemType | None] = {}

    for subject, path, unit_title_override in FILES:
        outline = extract_outline(path)
        unit_title = unit_title_override or outline.unit_title
        if not unit_title:
            continue
        for p in extract_problems(path):
            tier_name = _TIER_NAME_BY_STEP.get(p.tier)
            if tier_name is None:
                stats['other_tier'] += 1
                continue
            tier = tiers[p.tier]

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
