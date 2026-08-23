"""
hwp_sen_daepyo_parse.extract_representative_types()로 뽑은 쎈수학 "대표문제"
유형 목록을 taxonomy(Chapter > Section > SubSection > ProblemType)에 반영한다.

이 자료는 실제 유형명("수열의 수렴과 발산" 등)을 갖고 있으므로, RPM/수매씽처럼
순번 자리표시자("유형 N")가 아니라 진짜 이름으로 ProblemType을 만든다.
소단원 이름은 RPM/수매씽과 이미 합의된 정식 이름(SUBSECTION_MAP)을 그대로
써서 같은 소단원 아래 세 출처의 유형이 모두 모이게 한다.

대표문제 번호/정답은 (아직 쎈수학 개별 문제의 지문·이미지를 못 뽑았으므로)
Problem 행을 만들 재료가 없다 - ProblemType taxonomy만 세운다. 나중에 쎈수학
문제 PDF를 실제로 추출하게 되면, 이 HWP 자료를 다시 파싱해서
"현재 유형의 대표문제 번호 <= 문제번호 < 다음 유형의 대표문제 번호" 규칙으로
문제 -> 유형 매핑에 쓰면 된다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from hwp_sen_daepyo_parse import extract_representative_types
from import_workbook_outline import get_or_create_section, get_or_create_subsection
from models import Chapter, ProblemType, init_db

SUBJECT = '미적분2'

# 파일명(소단원별 1개) -> (중단원, 정식 소단원명). 정식 이름은 수매씽 교재의
# 실제 목차/구분 페이지로 검증된 이름이며, RPM도 이미 이 이름으로 정리했다
# (merge_rpm_subsection_names.py).
FILE_TO_SUBSECTION = {
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
}


def _match_subsection(filename: str) -> tuple[str, str] | None:
    for key, target in FILE_TO_SUBSECTION.items():
        if key in filename:
            return target
    return None


def insert_types(session: Session, filename: str, entries) -> int:
    """한 소단원 파일의 대표문제 목록을 ProblemType으로 반영한다.

    반환값: 새로 만든 ProblemType 수.
    """
    target = _match_subsection(filename)
    if target is None:
        raise ValueError(f'소단원 매핑을 찾을 수 없음: {filename}')
    section_name, subsection_name = target

    chapter = session.query(Chapter).filter_by(name=SUBJECT).one()
    section = get_or_create_section(session, chapter, section_name)
    subsection = get_or_create_subsection(session, section, subsection_name)

    created = 0
    for e in entries:
        code = f'{SUBJECT}-쎈-{subsection_name}-유형{e.type_no}'
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

    base_dir = sys.argv[1]

    engine = init_db()
    with Session(engine) as session:
        total = 0
        for filename in sorted(os.listdir(base_dir)):
            if not filename.endswith('.hwp'):
                continue
            path = os.path.join(base_dir, filename)
            entries = extract_representative_types(path)
            created = insert_types(session, filename, entries)
            total += created
            print(f'{filename}: 유형 {len(entries)}개 중 신규 {created}개')
        session.commit()
        print('총 신규 ProblemType:', total)
