"""자동 출제(Pillar 3): 대/중/소단원 + 유형 + 난이도 조건으로 문제를 뽑는다.

선택 기준은 전부 "지정하면 그 값으로 필터, 안 지정하면 전체" 방식으로
누적된다 (AND 조건). 난이도는 DB에 거의 안 채워져 있어(difficulty_score는
전무, difficulty_label은 NGD 1,361문제뿐, difficulty_tier는 구 3단계
문제집 3,236문제뿐) 있는 쪽에서만 걸리고, 없는 축은 그냥 무시된다.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Chapter, Section, SubSection, ProblemType, DifficultyTier, Problem


@dataclass
class WorksheetSelection:
    chapter: str
    sections: list[str] = field(default_factory=list)       # 비우면 전체 중단원
    subsections: list[str] = field(default_factory=list)     # 비우면 전체 소단원
    type_names: list[str] = field(default_factory=list)      # 비우면 전체 유형 (부분 문자열 매칭)
    difficulty_tiers: list[str] = field(default_factory=list)  # 예: ["핵심 유형", "심화 유형"]
    difficulty_labels: list[str] = field(default_factory=list)  # 예: ["중", "상"]
    count: int | None = None          # None이면 조건에 맞는 문제 전부
    per_type_count: int | None = None  # 지정하면 유형별로 이 개수만큼만 (부족하면 있는 만큼)
    shuffle: bool = False
    seed: int | None = None


def _base_query(session: Session, sel: WorksheetSelection):
    q = (
        select(Problem)
        .join(ProblemType, Problem.problem_type_id == ProblemType.id, isouter=True)
        .join(SubSection, ProblemType.subsection_id == SubSection.id, isouter=True)
        .join(Section, SubSection.section_id == Section.id, isouter=True)
        .join(Chapter, Section.chapter_id == Chapter.id, isouter=True)
        .join(DifficultyTier, Problem.difficulty_tier_id == DifficultyTier.id, isouter=True)
        .where(Chapter.name == sel.chapter)
    )
    if sel.sections:
        q = q.where(Section.name.in_(sel.sections))
    if sel.subsections:
        q = q.where(SubSection.name.in_(sel.subsections))
    if sel.type_names:
        conds = [ProblemType.name.like(f"%{t}%") for t in sel.type_names]
        from sqlalchemy import or_
        q = q.where(or_(*conds))
    if sel.difficulty_tiers:
        q = q.where(DifficultyTier.name.in_(sel.difficulty_tiers))
    if sel.difficulty_labels:
        q = q.where(Problem.difficulty_label.in_(sel.difficulty_labels))
    return q


def select_problems(session: Session, sel: WorksheetSelection) -> list[Problem]:
    """조건에 맞는 Problem 목록을 (대단원>중단원>소단원>유형 순서) 정렬해 반환한다.
    per_type_count가 지정되면 유형별로 그만큼만 뽑고(부족하면 있는 만큼),
    count가 지정되면 최종 결과를 그 개수로 자른다(shuffle 후 자르므로 무작위 추출 효과)."""
    q = _base_query(session, sel).order_by(
        Chapter.order, Section.order, SubSection.order, ProblemType.order, Problem.id
    )
    problems = list(session.execute(q).scalars().unique())

    if sel.per_type_count is not None:
        rng = random.Random(sel.seed)
        by_type: dict[int | None, list[Problem]] = {}
        for p in problems:
            by_type.setdefault(p.problem_type_id, []).append(p)
        picked: list[Problem] = []
        for type_id in sorted(by_type, key=lambda k: (k is None, k)):
            group = by_type[type_id]
            if sel.shuffle:
                rng.shuffle(group)
            picked.extend(group[: sel.per_type_count])
        problems = picked
        # 유형 순서를 유지하기 위해 원래 정렬 기준으로 다시 정렬
        order_index = {p.id: i for i, p in enumerate(session.execute(q).scalars().unique())}
        problems.sort(key=lambda p: order_index[p.id])

    if sel.shuffle:
        rng = random.Random(sel.seed)
        rng.shuffle(problems)

    if sel.count is not None:
        problems = problems[: sel.count]

    return problems


def describe_problem_path(p: Problem) -> str:
    """문제 하나의 위치를 '대단원 > 중단원 > 소단원 > 유형' 문자열로 만든다."""
    if p.problem_type is not None:
        pt = p.problem_type
        ss = pt.subsection
        sec = ss.section
        ch = sec.chapter
        return f"{ch.name} > {sec.name} > {ss.name} > {pt.name}"
    if p.difficulty_tier is not None:
        return f"(유형 미분류, 난이도: {p.difficulty_tier.name})"
    return "(미분류)"
