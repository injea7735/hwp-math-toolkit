"""NGD placeholder 아래 있는 미적분1 문제들을 실제 유형 재분류를 위해
unit별로 (id, stem 앞부분) 텍스트 덤프한다. 분류는 별도로 수동/LLM 판단 후
apply_ngd_reclassify.py로 적용한다."""
from __future__ import annotations
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from models import init_db, Problem, ProblemType, SubSection, Section, Chapter

STEM_CHARS = 220


def main():
    unit_name = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else f'ngd_dump_{unit_name}.txt'

    engine = init_db()
    with Session(engine) as s:
        rows = (
            s.query(Problem.id, Problem.stem_latex)
            .join(ProblemType, Problem.problem_type_id == ProblemType.id)
            .join(SubSection, ProblemType.subsection_id == SubSection.id)
            .join(Section, SubSection.section_id == Section.id)
            .join(Chapter, Section.chapter_id == Chapter.id)
            .filter(Chapter.name == 'NGD 가져오기', SubSection.name == unit_name)
            .order_by(Problem.id)
            .all()
        )
        lines = []
        for pid, stem in rows:
            stem = (stem or '').replace('\n', ' ').strip()
            lines.append(f'#{pid}| {stem[:STEM_CHARS]}')

    Path(out_path).write_text('\n'.join(lines), encoding='utf-8')
    print(f'{unit_name}: {len(rows)}건 -> {out_path}')


if __name__ == '__main__':
    main()
