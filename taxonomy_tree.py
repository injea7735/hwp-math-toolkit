"""대단원/중단원/소단원/유형 트리를 나열하는 순수 쿼리 함수 모음.

worksheet_app.py의 단원 탐색 UI가 드릴다운(대단원 -> 중단원 -> 소단원 -> 유형)할
때마다 호출한다. worksheet_select.py의 join 패턴을 그대로 따른다.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Chapter, DifficultyTier, Problem, ProblemType, Section, SubSection


def list_chapters(session: Session) -> list[dict]:
    q = select(Chapter).order_by(Chapter.order, Chapter.name)
    return [{"id": c.id, "name": c.name} for c in session.execute(q).scalars()]


def list_sections(session: Session, chapter_name: str) -> list[dict]:
    q = (
        select(Section)
        .join(Chapter, Section.chapter_id == Chapter.id)
        .where(Chapter.name == chapter_name)
        .order_by(Section.order, Section.name)
    )
    return [{"id": s.id, "name": s.name} for s in session.execute(q).scalars()]


def list_subsections(
    session: Session, chapter_name: str, section_names: list[str] | None = None,
) -> list[dict]:
    q = (
        select(SubSection)
        .join(Section, SubSection.section_id == Section.id)
        .join(Chapter, Section.chapter_id == Chapter.id)
        .where(Chapter.name == chapter_name)
        .order_by(SubSection.order, SubSection.name)
    )
    if section_names:
        q = q.where(Section.name.in_(section_names))
    return [{"id": ss.id, "name": ss.name} for ss in session.execute(q).scalars()]


def list_types(
    session: Session,
    chapter_name: str,
    section_names: list[str] | None = None,
    subsection_names: list[str] | None = None,
) -> list[dict]:
    q = (
        select(ProblemType, func.count(Problem.id))
        .join(SubSection, ProblemType.subsection_id == SubSection.id)
        .join(Section, SubSection.section_id == Section.id)
        .join(Chapter, Section.chapter_id == Chapter.id)
        .outerjoin(Problem, Problem.problem_type_id == ProblemType.id)
        .where(Chapter.name == chapter_name)
        .group_by(ProblemType.id)
        .order_by(ProblemType.order, ProblemType.name)
    )
    if section_names:
        q = q.where(Section.name.in_(section_names))
    if subsection_names:
        q = q.where(SubSection.name.in_(subsection_names))
    return [
        {"id": pt.id, "name": pt.name, "problem_count": count}
        for pt, count in session.execute(q).all()
    ]


def list_difficulty_tiers(session: Session) -> list[dict]:
    q = select(DifficultyTier).order_by(DifficultyTier.order, DifficultyTier.name)
    return [{"id": t.id, "name": t.name} for t in session.execute(q).scalars()]


_LABEL_ORDER = {"하": 0, "중": 1, "상": 2, "최상": 3}


def distinct_difficulty_labels(session: Session, chapter_name: str) -> list[str]:
    q = (
        select(Problem.difficulty_label)
        .join(ProblemType, Problem.problem_type_id == ProblemType.id, isouter=True)
        .join(SubSection, ProblemType.subsection_id == SubSection.id, isouter=True)
        .join(Section, SubSection.section_id == Section.id, isouter=True)
        .join(Chapter, Section.chapter_id == Chapter.id, isouter=True)
        .where(Chapter.name == chapter_name, Problem.difficulty_label.is_not(None))
        .distinct()
    )
    labels = [row[0] for row in session.execute(q).all()]
    return sorted(labels, key=lambda l: (_LABEL_ORDER.get(l, 99), l))


def distinct_question_kinds(session: Session, chapter_name: str) -> list[str]:
    q = (
        select(Problem.question_kind)
        .join(ProblemType, Problem.problem_type_id == ProblemType.id, isouter=True)
        .join(SubSection, ProblemType.subsection_id == SubSection.id, isouter=True)
        .join(Section, SubSection.section_id == Section.id, isouter=True)
        .join(Chapter, Section.chapter_id == Chapter.id, isouter=True)
        .where(Chapter.name == chapter_name)
        .distinct()
    )
    kinds = [row[0] for row in session.execute(q).all() if row[0]]
    return sorted(kinds)
