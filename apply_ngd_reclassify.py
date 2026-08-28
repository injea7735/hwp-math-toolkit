"""NGD placeholder 아래 있던 미적분1 문제들을, 내용 판단으로 결정한
(소단원, 유형order) 매핑에 따라 실제 ProblemType으로 재배정한다.

매핑 파일 형식: 한 줄에 "id|소단원명|order" (탭/파이프 구분), '#'으로 시작하면 주석.
"""
from __future__ import annotations
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from models import init_db, Problem, ProblemType, SubSection, Section, Chapter


def load_mapping(path: str) -> list[tuple[int, str, int]]:
    out = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        pid_s, subsection, order_s = line.split('|')
        out.append((int(pid_s), subsection.strip(), int(order_s)))
    return out


def apply_mapping(session: Session, mapping: list[tuple[int, str, int]]) -> int:
    type_cache: dict[tuple[str, int], ProblemType] = {}
    changed = 0
    for pid, subsection_name, order in mapping:
        key = (subsection_name, order)
        if key not in type_cache:
            pt = (
                session.query(ProblemType)
                .join(SubSection, ProblemType.subsection_id == SubSection.id)
                .join(Section, SubSection.section_id == Section.id)
                .join(Chapter, Section.chapter_id == Chapter.id)
                .filter(
                    Chapter.name == '미적분1',
                    SubSection.name == subsection_name,
                    ProblemType.order == order,
                )
                .one_or_none()
            )
            if pt is None:
                raise ValueError(f'ProblemType 없음: 미적분1 > {subsection_name} > 유형{order:02d}')
            type_cache[key] = pt

        p = session.get(Problem, pid)
        if p is None:
            raise ValueError(f'Problem #{pid} 없음')
        p.problem_type_id = type_cache[key].id
        changed += 1
    return changed


if __name__ == '__main__':
    mapping_path = sys.argv[1]
    engine = init_db()
    with Session(engine) as session:
        mapping = load_mapping(mapping_path)
        changed = apply_mapping(session, mapping)
        session.commit()
        print(f'{changed}건 재배정 완료 ({mapping_path})')
