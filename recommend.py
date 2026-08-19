"""학생의 취약 유형(ProblemType)을 기준으로 문제를 뽑아주는 추천 로직."""
from __future__ import annotations
import random
from collections import defaultdict

from sqlalchemy.orm import Session

from models import Attempt, Problem


def _type_ids_by_accuracy(attempts: list[Attempt], min_attempts: int) -> list[int]:
    """시도 목록을 유형별 정답률로 집계해, 정답률이 낮은 순으로 유형 id 목록을 반환한다.
    시도 횟수가 min_attempts 미만인 유형은 (신뢰도가 낮아) 제외한다."""
    stats: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # type_id -> [correct, total]
    for a in attempts:
        s = stats[a.problem.problem_type_id]
        s[1] += 1
        if a.is_correct:
            s[0] += 1

    ranked = [
        (type_id, correct / total)
        for type_id, (correct, total) in stats.items()
        if total >= min_attempts
    ]
    ranked.sort(key=lambda pair: pair[1])
    return [type_id for type_id, _ in ranked]


def weak_problem_type_ids(session: Session, student_id: int, min_attempts: int = 3) -> list[int]:
    """학생 개인의 유형별 정답률을 계산해, 정답률이 낮은 순으로 유형 id 목록을 반환한다."""
    attempts = (
        session.query(Attempt)
        .join(Problem, Attempt.problem_id == Problem.id)
        .filter(Attempt.student_id == student_id)
        .all()
    )
    return _type_ids_by_accuracy(attempts, min_attempts)


def globally_weak_problem_type_ids(session: Session, min_attempts: int = 10) -> list[int]:
    """개인이 아니라 전체 학생의 시도를 합산해, 정답률이 낮은 순으로 유형 id 목록을 반환한다.
    유형 자체가 전반적으로 어려운지를 판단하는 용도 (개인 데이터가 부족한 학생에게도 적용 가능)."""
    attempts = session.query(Attempt).join(Problem, Attempt.problem_id == Problem.id).all()
    return _type_ids_by_accuracy(attempts, min_attempts)


def pick_problems_for_student(
    session: Session,
    student_id: int,
    count: int = 5,
    min_attempts: int = 3,
    global_min_attempts: int = 10,
) -> list[Problem]:
    """학생의 취약 유형 + 전체 학생 기준 취약 유형에서 문제를 뽑는다.

    - 이 학생 개인의 취약 유형을 최우선으로 채운다.
    - 남은 자리는, 개인 데이터가 없거나 부족하더라도 전체 학생이 많이 틀리는
      유형(globally_weak_problem_type_ids)에서 채운다.
    - 같은 유형 안에서는 아직 안 푼 문제 / 최근 시도가 오답인 문제를 먼저 뽑고,
      최근에 맞힌 문제는 뒤로 미룬다 (이미 아는 문제 반복을 피하기 위함).
    - 그래도 count를 못 채우면 나머지 문제 중 무작위로 채운다.
    """
    personal_weak = weak_problem_type_ids(session, student_id, min_attempts)
    global_weak = globally_weak_problem_type_ids(session, global_min_attempts)

    weak_type_ids: list[int] = []
    seen_type_ids: set[int] = set()
    for type_id in personal_weak + global_weak:
        if type_id not in seen_type_ids:
            seen_type_ids.add(type_id)
            weak_type_ids.append(type_id)

    last_result: dict[int, bool] = {}
    for a in (
        session.query(Attempt)
        .filter(Attempt.student_id == student_id)
        .order_by(Attempt.answered_at)
    ):
        last_result[a.problem_id] = a.is_correct

    def recently_solved_correctly(problem: Problem) -> bool:
        return last_result.get(problem.id) is True

    picked: list[Problem] = []
    picked_ids: set[int] = set()

    for type_id in weak_type_ids:
        if len(picked) >= count:
            break
        candidates = session.query(Problem).filter(Problem.problem_type_id == type_id).all()
        candidates.sort(key=recently_solved_correctly)
        for p in candidates:
            if len(picked) >= count:
                break
            if p.id not in picked_ids:
                picked.append(p)
                picked_ids.add(p.id)

    if len(picked) < count:
        remaining = session.query(Problem).filter(Problem.id.notin_(picked_ids)).all()
        random.shuffle(remaining)
        for p in remaining:
            if len(picked) >= count:
                break
            picked.append(p)
            picked_ids.add(p.id)

    return picked[:count]
