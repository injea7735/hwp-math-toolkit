"""
hwp_sen_daepyo_parse.extract_representative_types()로 뽑은 쎈수학 "대표문제"
유형 목록을 taxonomy(Chapter > Section > SubSection > ProblemType)에 반영한다.

이 자료는 실제 유형명("수열의 수렴과 발산" 등)을 갖고 있으므로, RPM/수매씽처럼
순번 자리표시자("유형 N")가 아니라 진짜 이름으로 ProblemType을 만든다.
소단원 이름은 다른 출처(RPM/수매씽 등)와 이미 합의된 정식 이름을 그대로 써서
같은 소단원 아래 여러 출처의 유형이 모두 모이게 한다 - 과목별 매핑은
`pdf_sen_extract.py`의 `*_SUBSECTION_ORDER` 상수와 짝이 맞아야 한다.

대표문제 번호/정답은 이미지 pipeline이 없는 과목이면 Problem 행을 만들
재료가 없다 - 그럴 땐 ProblemType taxonomy만 세운다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from hwp_sen_daepyo_parse import extract_representative_types
from import_workbook_outline import get_or_create_section, get_or_create_subsection
from models import Chapter, ProblemType, init_db

# 파일명(소단원별 1개) -> (중단원, 정식 소단원명). pdf_sen_extract.py의
# 해당 과목 *_SUBSECTION_ORDER와 같은 순서/이름을 써야 한다.
FILE_TO_SUBSECTION_BY_SUBJECT: dict[str, dict[str, tuple[str, str]]] = {
    '미적분2': {
        '01 수열의 극한': ('수열의 극한', '수열의 극한'),
        '02 급수': ('수열의 극한', '급수'),
        '03 지수함수와 로그함수의 미분': ('미분법', '지수함수와 로그함수의 미분'),
        '04 삼각함수의 미분': ('미분법', '삼각함수의 미분'),
        '05 여러 가지 미분법': ('미분법', '여러 가지 미분법'),
        '06 도함수의 활용 (1)': ('미분법', '도함수의 활용 ⑴'),
        '07 도함수의 활용 (2)': ('미분법', '도함수의 활용 ⑵'),
        '08 여러 가지 함수의 적분법': ('적분법', '여러 가지 적분법'),
        '09 치환적분법과 부분적분법': ('적분법', '정적분'),
        '10 정적분의 활용': ('적분법', '정적분의 활용'),
    },
    '대수': {
        '01 지수': ('지수함수와 로그함수', '지수'),
        '02 로그': ('지수함수와 로그함수', '로그'),
        '03 지수함수': ('지수함수와 로그함수', '지수함수'),
        '04 로그함수': ('지수함수와 로그함수', '로그함수'),
        '05 삼각함수': ('삼각함수', '삼각함수'),
        '06 삼각함수의 그래프': ('삼각함수', '삼각함수의 그래프'),
        '07 삼각함수의 활용': ('삼각함수', '삼각함수의 활용'),
        '08 등차수열과 등비수열': ('수열', '등차수열과 등비수열'),
        '09 수열의 합': ('수열', '수열의 합'),
        '10 수학적 귀납법': ('수열', '수학적 귀납법'),
    },
    # 22개정 미적분Ⅰ용 쎈 유형서가 없어서 구교육과정 "수학Ⅱ" 쎈 대표문제
    # HWP를 대신 쓴다(2026-08-23) - 파일명이 '+' 구분자를 쓴다(다운로드 원본 그대로).
    '미적분1': {
        '01+함수의+극한': ('함수의 극한과 연속', '함수의 극한'),
        '02+함수의+연속': ('함수의 극한과 연속', '함수의 연속'),
        '03+미분계수와+도함수': ('미분', '미분계수와 도함수'),
        '04+도함수의+활용⑴': ('미분', '도함수의 활용 ⑴'),
        '05+도함수의+활용⑵': ('미분', '도함수의 활용 ⑵'),
        '06+도함수의+활용⑶': ('미분', '도함수의 활용 ⑶'),
        '07+부정적분': ('적분', '부정적분'),
        '08+정적분': ('적분', '정적분'),
        '09+정적분의+활용': ('적분', '정적분의 활용'),
    },
    '확률과 통계': {
        '01 여러 가지 순열': ('경우의 수', '여러 가지 순열'),
        '02 중복조합과 이항정리': ('경우의 수', '중복조합과 이항정리'),
        '03 확률의 뜻과 활용': ('확률', '확률의 뜻과 활용'),
        '04 조건부확률': ('확률', '조건부확률'),
        '05 확률변수와 확률분포': ('통계', '확률변수와 확률분포'),
        '06 이항분포와 정규분포': ('통계', '이항분포와 정규분포'),
        '07 통계적 추정': ('통계', '통계적 추정'),
    },
}


def _match_subsection(filename: str, file_to_subsection: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    for key, target in file_to_subsection.items():
        if key in filename:
            return target
    return None


def insert_types(session: Session, subject: str, filename: str, entries) -> int:
    """한 소단원 파일의 대표문제 목록을 ProblemType으로 반영한다.

    반환값: 새로 만든 ProblemType 수.
    """
    file_to_subsection = FILE_TO_SUBSECTION_BY_SUBJECT[subject]
    target = _match_subsection(filename, file_to_subsection)
    if target is None:
        raise ValueError(f'소단원 매핑을 찾을 수 없음: {filename}')
    section_name, subsection_name = target

    chapter = session.query(Chapter).filter_by(name=subject).one()
    section = get_or_create_section(session, chapter, section_name)
    subsection = get_or_create_subsection(session, section, subsection_name)

    created = 0
    for e in entries:
        code = f'{subject}-쎈-{subsection_name}-유형{e.type_no}'
        ptype = session.query(ProblemType).filter_by(code=code).one_or_none()
        if ptype is None:
            ptype = ProblemType(
                subsection_id=subsection.id, code=code,
                name=e.title, order=int(e.type_no),
            )
            session.add(ptype)
            session.flush()
            created += 1
    return created


if __name__ == '__main__':
    import os
    import sys

    subject = sys.argv[1]
    base_dir = sys.argv[2]

    engine = init_db()
    with Session(engine) as session:
        total = 0
        for filename in sorted(os.listdir(base_dir)):
            if not filename.endswith('.hwp'):
                continue
            path = os.path.join(base_dir, filename)
            entries = extract_representative_types(path)
            created = insert_types(session, subject, filename, entries)
            total += created
            print(f'{filename}: 유형 {len(entries)}개 중 신규 {created}개')
        session.commit()
        print('총 신규 ProblemType:', total)
