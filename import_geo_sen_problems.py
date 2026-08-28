"""
pdf_geo_sen_extract.extract_problems()로 뽑은 쎈수학 기하 문제를
models.Problem에 넣는다. import_mi1_sen_problems.py와 같은 구조 - 대표문제
HWP 인덱스가 없어 정답(answer)은 채우지 않는다.

ProblemType은 import_geo_sen_types.py가 이미 실제 유형명으로 만들어 뒀으므로
(code=f'{subject}-쎈-{subsection_name}-유형{type_no}') 그걸 그대로 찾아 쓴다.
"""
from __future__ import annotations

import json
import re

from PIL import Image
from sqlalchemy.orm import Session

from models import Chapter, Problem, ProblemType, Source, init_db
from pdf_mi1_sen_extract import Mi1Problem

_FALLBACK_NAME_RE = re.compile(r'_col\d+-\d+\.png$')
_TALL_CROP_PX = 1300

SUBJECT = '기하'


def _get_or_create_source(session: Session, pdf_path: str) -> Source:
    exam_name = f'{SUBJECT} 쎈수학 유형서(PDF)'
    src = session.query(Source).filter_by(exam_name=exam_name).one_or_none()
    if src is None:
        src = Source(exam_name=exam_name, material_kind='N제')
        session.add(src)
        session.flush()
    return src


def insert_problems(session: Session, problems: list[Mi1Problem], pdf_path: str | None = None) -> int:
    session.query(Chapter).filter_by(name=SUBJECT).one()  # 존재 확인
    source = _get_or_create_source(session, pdf_path or '')

    type_cache: dict[str, ProblemType] = {}
    created = 0

    for p in problems:
        code = f'{SUBJECT}-쎈-{p.subsection_name}-유형{p.type_no}'
        ptype = type_cache.get(code)
        if ptype is None:
            ptype = session.query(ProblemType).filter_by(code=code).one_or_none()
            if ptype is None:
                raise ValueError(f'ProblemType 없음: {code} - import_geo_sen_types.py를 먼저 실행하세요')
            type_cache[code] = ptype

        image_paths_json = json.dumps([p.image_path], ensure_ascii=False)
        exists = session.query(Problem).filter_by(image_paths=image_paths_json).one_or_none()
        if exists is not None:
            continue

        needs_review = bool(_FALLBACK_NAME_RE.search(p.image_path))
        if not needs_review:
            try:
                with Image.open(p.image_path) as img:
                    needs_review = img.height > _TALL_CROP_PX
            except Exception:
                needs_review = True

        session.add(Problem(
            problem_type_id=ptype.id,
            source_id=source.id,
            stem_latex='(이미지 참고)',
            question_kind='객관식',
            image_paths=image_paths_json,
            original_file_path=pdf_path,
            source_page_index=p.page_index,
            needs_review=needs_review,
        ))
        created += 1

    return created


if __name__ == '__main__':
    import sys

    from pdf_geo_sen_extract import GEO_SUBSECTION_ORDER, TOC_PAGE_INDICES, extract_problems
    from pdf_mi1_toc_parse import parse_toc_pages

    pdf_path = sys.argv[1]
    out_dir = sys.argv[2]

    toc = parse_toc_pages(pdf_path, TOC_PAGE_INDICES, [name for _, name in GEO_SUBSECTION_ORDER])
    problems, warnings = extract_problems(pdf_path, out_dir, GEO_SUBSECTION_ORDER, toc)
    print('추출된 문제 수:', len(problems), '경고:', len(warnings))

    engine = init_db()
    with Session(engine) as session:
        created = insert_problems(session, problems, pdf_path)
        session.commit()
        print('DB에 새로 넣은 문제 수:', created)
