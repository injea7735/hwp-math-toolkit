"""1회성 수동 보정: 소단원 경계 등에서 순번 카운터/재동기화가 못 잡은
드리프트를, 직접 원본 페이지를 읽어 확인한 (실제 유형번호 -> 대표문제
번호) 앵커 목록으로 재배정한다. 같은 소단원 안의 모든 Problem 행(파일명에
박힌 4자리 번호 기준)을 앵커 구간에 맞춰 problem_type_id를 고쳐 쓴다."""
from __future__ import annotations

import json
import re
import sys

from sqlalchemy.orm import Session

from models import init_db, Problem, ProblemType, Source

_NUM_RE = re.compile(r'_(\d{4})(?:\.png)?$')


def apply_anchors(session: Session, source_id: int, subsection_name: str, anchors: list[tuple[str, int]]):
    """anchors: [(real_type_no, daepyo_number), ...] 오름차순.

    이 소단원의 유형 전부에 대한 앵커가 있어야 한다 - 일부만 주면 마지막
    앵커보다 큰 번호가 전부 그 마지막 유형으로 잘못 쓸려 들어가(실제로
    두 번 겪음: 이미 정상이던 뒤쪽 유형들의 데이터가 덮어써짐), 멀쩡했던
    데이터까지 망가뜨린다."""
    anchors = sorted(anchors, key=lambda a: a[1])
    types = {
        t.code.rsplit('유형', 1)[1]: t
        for t in session.query(ProblemType).filter(
            ProblemType.code.contains(f'-쎈-{subsection_name}-유형')
        ).all()
    }
    given_nos = {no for no, _ in anchors}
    missing = sorted(set(types) - given_nos, key=lambda n: int(n))
    if missing:
        raise ValueError(
            f'{subsection_name}: 앵커 누락 - 유형 {missing} (전체 {sorted(types, key=lambda n: int(n))}). '
            f'전체 유형에 앵커를 다 줘야 마지막 유형이 뒤쪽 데이터를 잘못 흡수하지 않는다.'
        )
    type_ids_in_sub = {t.id for t in types.values()}

    probs = session.query(Problem).filter(
        Problem.source_id == source_id, Problem.problem_type_id.in_(type_ids_in_sub)
    ).all()

    changed = 0
    for p in probs:
        path = json.loads(p.image_paths)[0]
        m = _NUM_RE.search(path)
        if m is None:
            continue
        num = int(m.group(1))
        target_no = None
        for real_no, anchor_num in anchors:
            if num >= anchor_num:
                target_no = real_no
            else:
                break
        if target_no is None:
            continue
        target_type = types[target_no]
        if p.problem_type_id != target_type.id:
            p.problem_type_id = target_type.id
            changed += 1
    return changed


if __name__ == '__main__':
    subject_exam = sys.argv[1]
    subsection = sys.argv[2]
    anchor_pairs = sys.argv[3:]  # "01=0157" "02=0162" ...
    anchors = []
    for pair in anchor_pairs:
        no, num = pair.split('=')
        anchors.append((no, int(num)))

    engine = init_db()
    with Session(engine) as session:
        src = session.query(Source).filter_by(exam_name=subject_exam).one()
        changed = apply_anchors(session, src.id, subsection, anchors)
        session.commit()
        print(f'{subsection}: {changed}건 재배정')
