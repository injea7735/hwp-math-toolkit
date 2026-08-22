"""
hwp_workbook_parse.extract_problems()로 재구성한 문제를 models.Problem
테이블에 넣는다.

유형(ProblemType)은 import_workbook_outline.py로 이미 taxonomy에 들어가
있어야 한다 — code(f"{subject}-{unit_title}-{no}")로 찾는다. 아직 없는
유형이면 그 문제는 건너뛰고 개수를 따로 센다(먼저 outline을 넣으라는 신호).

재실행해도 같은 유형 안에 같은 지문(stem_latex)이 이미 있으면 건너뛴다
(idempotent) — hwp_workbook_parse가 아직 완벽하지 않아 재추출 결과가
바뀔 수 있으므로, 완전한 자연키보다는 "지문 텍스트 중복 여부"로 단순하게 판단한다.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from hwp_workbook_parse import extract_outline, extract_problems, Problem as ParsedProblem
from models import Problem, ProblemType, init_db

_CHOICE_MARKER_RE = re.compile(r'[①②③④⑤]')


def guess_question_kind(answer: str) -> str:
    if '풀이 참조' in answer:
        return '서술형'
    if _CHOICE_MARKER_RE.search(answer):
        return '객관식'
    return '단답형'


_CHOICE_ORDER = '①②③④⑤'


def split_choices(stem: str) -> tuple[str, list[str] | None]:
    """지문 끝에 ①②③④⑤ 로 붙어 있는 객관식 보기 5개를 분리한다.

    풀이 설명 중간에 "①의 경우 ~, ②의 경우 ~"처럼 보기 번호를 다시 언급하는
    문제가 실제 자료에 있어서, 그냥 첫 번째 마커부터 자르면 지문이 통째로
    날아간다. 그래서 뒤에서부터 ⑤ -> ① 순서로 거슬러 올라가며 "마지막으로
    등장하는, 순서가 맞는 5개짜리 블록"만 진짜 보기로 인정한다. 5개를 모두
    못 찾거나 그 앞에 지문이 하나도 안 남으면 분리하지 않는다.
    """
    search_end = len(stem)
    positions = {}
    for ch in reversed(_CHOICE_ORDER):  # ⑤, ④, ③, ②, ① 순서로 거꾸로 탐색
        idx = stem.rfind(ch, 0, search_end)
        if idx == -1:
            return stem, None
        positions[ch] = idx
        search_end = idx

    start = positions[_CHOICE_ORDER[0]]
    body = stem[:start].strip()
    if not body:
        return stem, None

    choices = []
    for i, ch in enumerate(_CHOICE_ORDER):
        seg_start = positions[ch] + 1
        seg_end = positions[_CHOICE_ORDER[i + 1]] if i + 1 < len(_CHOICE_ORDER) else len(stem)
        choices.append(stem[seg_start:seg_end].strip())
    return body, choices


def insert_problems(
    session: Session,
    subject: str,
    unit_title: str,
    parsed: list[ParsedProblem],
    source_path: str | None = None,
) -> tuple[int, int]:
    """반환값: (신규 삽입 수, 유형을 못 찾아 건너뛴 수)"""
    created = 0
    skipped_no_type = 0
    type_cache: dict[str, ProblemType | None] = {}

    for p in parsed:
        code = f"{subject}-{unit_title}-{p.type_no}"
        if code not in type_cache:
            type_cache[code] = session.query(ProblemType).filter_by(code=code).one_or_none()
        ptype = type_cache[code]
        if ptype is None:
            skipped_no_type += 1
            continue

        body, choices = split_choices(p.stem)

        exists = (
            session.query(Problem)
            .filter_by(problem_type_id=ptype.id, stem_latex=body)
            .one_or_none()
        )
        if exists is not None:
            continue

        session.add(Problem(
            problem_type_id=ptype.id,
            stem_latex=body,
            choices_latex=json.dumps(choices, ensure_ascii=False) if choices else None,
            answer=p.answer,
            question_kind=guess_question_kind(p.answer),
            original_file_path=source_path,
        ))
        created += 1

    return created, skipped_no_type


def import_problems_file(
    session: Session, subject: str, path: str, unit_title_override: str | None = None,
) -> tuple[int, int]:
    outline = extract_outline(path)
    unit_title = unit_title_override or outline.unit_title
    if not unit_title:
        return 0, 0
    parsed = extract_problems(path)
    return insert_problems(session, subject, unit_title, parsed, source_path=path)


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print('usage: import_workbook_problems.py <subject> <hwp파일...>')
        raise SystemExit(1)

    subject = sys.argv[1]
    paths = sys.argv[2:]

    engine = init_db()
    with Session(engine) as session:
        total_created, total_skipped = 0, 0
        for p in paths:
            created, skipped = import_problems_file(session, subject, p)
            print(f'{p}: +{created} (유형 없어 건너뜀 {skipped})')
            total_created += created
            total_skipped += skipped
        session.commit()
        print('총 신규 문제:', total_created, '/ 유형 없어 건너뜀:', total_skipped)
