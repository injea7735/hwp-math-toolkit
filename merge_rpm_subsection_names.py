"""
1회성 정리 스크립트: RPM 소단원 이름이 수매씽(검증된 정식 이름)과 달라서
생겼던 중복 소단원 2개를 정식 이름 쪽으로 합친다.

  '여러 가지 함수의 적분'   -> '여러 가지 적분법'
  '치환적분법과 부분적분법' -> '정적분'

각 중복 소단원은 RPM이 만든 placeholder ProblemType 1개, Problem 1건만
가지고 있다(소단원 단위 저장 방식). 그 Problem의 problem_type_id를 정식
소단원 쪽 placeholder ProblemType으로 옮기고, 빈 중복 ProblemType/SubSection을
지운다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from models import Chapter, Problem, ProblemType, SubSection, init_db

SUBJECT = '미적분2'
RENAMES = [
    ('여러 가지 함수의 적분', '여러 가지 적분법'),
    ('치환적분법과 부분적분법', '정적분'),
]


def merge(session: Session) -> None:
    chapter = session.query(Chapter).filter_by(name=SUBJECT).one()
    section = next(s for s in chapter.sections if s.name == '적분법')

    for old_name, canonical_name in RENAMES:
        old_sub = session.query(SubSection).filter_by(section_id=section.id, name=old_name).one_or_none()
        canonical_sub = session.query(SubSection).filter_by(section_id=section.id, name=canonical_name).one()
        if old_sub is None:
            print(f'  (건너뜀: {old_name} 없음)')
            continue

        canonical_code = f'{SUBJECT}-{canonical_name}-전체'
        canonical_ptype = session.query(ProblemType).filter_by(code=canonical_code).one_or_none()
        if canonical_ptype is None:
            canonical_ptype = ProblemType(
                subsection_id=canonical_sub.id, code=canonical_code, name='전체(소단원 단위로만 구분)',
            )
            session.add(canonical_ptype)
            session.flush()

        moved = 0
        for old_ptype in list(old_sub.problem_types):
            for p in session.query(Problem).filter_by(problem_type_id=old_ptype.id).all():
                p.problem_type_id = canonical_ptype.id
                moved += 1
            session.delete(old_ptype)
        session.delete(old_sub)
        print(f'  {old_name} -> {canonical_name}: Problem {moved}건 이전, 중복 소단원 삭제')


if __name__ == '__main__':
    engine = init_db()
    with Session(engine) as session:
        merge(session)
        session.commit()
        print('완료')
