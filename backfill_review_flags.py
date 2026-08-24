"""
1회성 스크립트: import_sen_problems.py에 needs_review/source_page_index
필드를 추가하기 전에 이미 들어간 쎈수학 Problem 행들을 채워 넣는다.
새로 들어오는 행은 import_sen_problems.py가 알아서 채우므로, 이 파일은
과거 데이터를 맞추는 용도로만 쓴다.
"""
from __future__ import annotations

import json
import re

from PIL import Image
from sqlalchemy.orm import Session

from import_sen_problems import _FALLBACK_NAME_RE, _TALL_CROP_PX
from models import Problem, Source, init_db

_PAGE_RE = re.compile(r'_(\d{4})_[^_]+\.png$')

SEN_SOURCES = ['미적분2 쎈수학 유형서(PDF)', '대수 쎈수학 유형서(PDF)', '확률과 통계 쎈수학 유형서(PDF)']


def backfill(session: Session) -> tuple[int, int]:
    updated = 0
    flagged = 0
    for exam_name in SEN_SOURCES:
        src = session.query(Source).filter_by(exam_name=exam_name).one_or_none()
        if src is None:
            continue
        for p in session.query(Problem).filter_by(source_id=src.id).all():
            path = json.loads(p.image_paths)[0]
            m = _PAGE_RE.search(path)
            if m:
                p.source_page_index = int(m.group(1))

            needs_review = bool(_FALLBACK_NAME_RE.search(path))
            if not needs_review:
                try:
                    with Image.open(path) as img:
                        needs_review = img.height > _TALL_CROP_PX
                except Exception:
                    needs_review = True
            p.needs_review = needs_review
            if needs_review:
                flagged += 1
            updated += 1
    return updated, flagged


if __name__ == '__main__':
    engine = init_db()
    with Session(engine) as session:
        updated, flagged = backfill(session)
        session.commit()
        print(f'업데이트 {updated}건, 검토 필요 {flagged}건')
