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
    question_kinds: list[str] = field(default_factory=list)  # 예: ["객관식", "서술형", "단답형"]
    count: int | None = None          # None이면 조건에 맞는 문제 전부
    per_type_count: int | None = None  # 지정하면 유형별로 이 개수만큼만 (부족하면 있는 만큼)
    # {"하": 2, "중": 5, "상": 3} 처럼 난이도(라벨 또는 tier 이름) 비율을 주면
    # count 전체를 그 비율대로 배분해서 뽑는다. difficulty_labels/difficulty_tiers
    # 필터와 별개로, "이 축의 값이 이 키들 중 하나인 문제만" + "비율대로" 동작한다.
    difficulty_ratio: dict[str, int] | None = None
    shuffle: bool = False
    seed: int | None = None


def _difficulty_key(p: Problem) -> str | None:
    """문제 하나의 난이도를 나타내는 키. difficulty_label이 있으면 그걸,
    없으면 difficulty_tier 이름을, 둘 다 없으면 None을 반환한다."""
    if p.difficulty_label:
        return p.difficulty_label
    if p.difficulty_tier is not None:
        return p.difficulty_tier.name
    return None


def _allocate_ratio_counts(total: int, ratio: dict[str, int]) -> dict[str, int]:
    """total개를 ratio 가중치대로 정수 배분한다 (최대 나머지법 - 배분 합이
    정확히 total이 되도록 보장)."""
    weight_sum = sum(ratio.values())
    if weight_sum <= 0:
        return {k: 0 for k in ratio}
    exact = {k: total * w / weight_sum for k, w in ratio.items()}
    base = {k: int(v) for k, v in exact.items()}
    remainder = total - sum(base.values())
    order = sorted(ratio.keys(), key=lambda k: exact[k] - base[k], reverse=True)
    for k in order[:remainder]:
        base[k] += 1
    return base


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
    if sel.question_kinds:
        q = q.where(Problem.question_kind.in_(sel.question_kinds))
    return q


def select_problems(session: Session, sel: WorksheetSelection) -> list[Problem]:
    """조건에 맞는 Problem 목록을 (대단원>중단원>소단원>유형 순서) 정렬해 반환한다.
    difficulty_ratio가 지정되면 count를 그 비율대로 배분해서 뽑고(다른 배분
    로직보다 우선), per_type_count가 지정되면 유형별로 그만큼만 뽑고(부족하면
    있는 만큼), count가 지정되면 최종 결과를 그 개수로 자른다(shuffle 후
    자르므로 무작위 추출 효과)."""
    q = _base_query(session, sel).order_by(
        Chapter.order, Section.order, SubSection.order, ProblemType.order, Problem.id
    )
    problems = list(session.execute(q).scalars().unique())

    if sel.difficulty_ratio and sel.count is not None:
        targets = _allocate_ratio_counts(sel.count, sel.difficulty_ratio)
        rng = random.Random(sel.seed)
        by_key: dict[str, list[Problem]] = {}
        for p in problems:
            k = _difficulty_key(p)
            if k in targets:
                by_key.setdefault(k, []).append(p)
        for group in by_key.values():
            if sel.shuffle:
                rng.shuffle(group)

        picked: list[Problem] = []
        taken: dict[str, int] = {}
        for key, target in targets.items():
            group = by_key.get(key, [])
            take = min(target, len(group))
            picked.extend(group[:take])
            taken[key] = take

        # 어느 난이도 버킷이 목표보다 적으면(비율대로는 못 채움), 다른
        # 버킷에 남는 문제로 부족분을 채워서 최대한 count를 맞춘다 - 비율은
        # "가능하면 이렇게"이지, 각 버킷의 상한을 깨서까지 count를 못 채우게
        # 하는 하드 캡이 아니다.
        shortfall = sel.count - len(picked)
        if shortfall > 0:
            for key in targets:
                if shortfall <= 0:
                    break
                group = by_key.get(key, [])
                extra = group[taken[key]: taken[key] + shortfall]
                picked.extend(extra)
                shortfall -= len(extra)

        order_index = {p.id: i for i, p in enumerate(problems)}
        picked.sort(key=lambda p: order_index[p.id])
        problems = picked

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
