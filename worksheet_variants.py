"""같은 문제 선택으로 A형/B형 등 여러 버전을 만든다 (문제 순서, 객관식
보기 순서를 서로 다르게 섞어서). 보기를 섞을 때는 원래 정답(①②③...)이
가리키던 실제 보기 내용을 추적해서, 섞인 뒤의 올바른 위치로 정답 표시를
다시 계산한다 - 단순 순서 셔플만 하면 정답이 틀어진다."""
from __future__ import annotations
import json
import random
from dataclasses import dataclass, field

from models import Problem

_CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧']


@dataclass
class WorksheetVariant:
    """한 버전(A형/B형 등)의 렌더링 데이터. problems[i]에 대응하는 보기 순서와
    실제 정답 표시가 choice_orders[i]/display_answers[i]에 담긴다."""
    name: str
    problems: list[Problem]
    choice_orders: list[list[int] | None] = field(default_factory=list)
    display_answers: list[str | None] = field(default_factory=list)


def _original_choice_index(answer: str | None) -> int | None:
    if not answer:
        return None
    for i, c in enumerate(_CIRCLED):
        if c in answer:
            return i
    return None


def _shuffle_choices(p: Problem, rng: random.Random) -> tuple[list[int] | None, str | None]:
    if not p.choices_latex:
        return None, p.answer
    try:
        choices = json.loads(p.choices_latex)
    except (json.JSONDecodeError, TypeError):
        return None, p.answer
    if not choices:
        return None, p.answer

    order = list(range(len(choices)))
    rng.shuffle(order)

    orig_idx = _original_choice_index(p.answer)
    if orig_idx is not None and orig_idx < len(choices):
        new_pos = order.index(orig_idx)
        display_answer = _CIRCLED[new_pos] if new_pos < len(_CIRCLED) else str(new_pos + 1)
    else:
        display_answer = p.answer  # 단답형/서술형 등 보기와 무관한 정답은 그대로
    return order, display_answer


def make_variants(
    problems: list[Problem],
    form_names: list[str],
    shuffle_problem_order: bool = True,
    shuffle_choices: bool = True,
    seed: int | None = None,
) -> list[WorksheetVariant]:
    """form_names(예: ["A", "B"]) 각각에 대해 독립적으로 섞은 버전을 만든다.
    seed가 주어지면 형(form) 이름별로 서로 다르지만 재현 가능한 시드를 쓴다."""
    variants = []
    for form in form_names:
        form_seed = None if seed is None else hash((seed, form)) & 0xFFFFFFFF
        rng = random.Random(form_seed)

        ordered = list(problems)
        if shuffle_problem_order:
            rng.shuffle(ordered)

        choice_orders: list[list[int] | None] = []
        display_answers: list[str | None] = []
        for p in ordered:
            if shuffle_choices:
                order, ans = _shuffle_choices(p, rng)
            else:
                order, ans = None, p.answer
            choice_orders.append(order)
            display_answers.append(ans)

        variants.append(WorksheetVariant(
            name=form, problems=ordered, choice_orders=choice_orders, display_answers=display_answers,
        ))
    return variants
