"""자동 출제(Pillar 3) CLI: 대/중/소단원+유형+난이도 조건으로 문제를 뽑아
HTML 시험지와 HWP 시험지를 동시에 생성한다. A형/B형 등 여러 버전, 난이도
비율 배분, 정답지 분리 생성도 지원한다.

예:
  python generate_worksheet.py --chapter 미적분1 --subsection "도함수의 활용 ⑵" \
      --type "함수의 극대" --count 10 --title "도함수의 활용 소단원 평가" \
      --out worksheets/deriv_app2

  # A형/B형 두 버전, 난이도 하:중:상 = 2:5:3 비율로 20문제, 정답지 분리
  python generate_worksheet.py --chapter 미적분1 --count 20 \
      --label-ratio "하:2,중:5,상:3" --form A --form B --separate-answer-key \
      --title "중간고사 대비" --out worksheets/midterm
"""
from __future__ import annotations
import argparse

from sqlalchemy.orm import Session

from models import init_db
from worksheet_select import WorksheetSelection, select_problems, describe_problem_path
from worksheet_variants import make_variants
from worksheet_render_html import save_worksheet_html, save_answer_key_html
from worksheet_render_hwp import save_worksheet_hwp, save_answer_key_hwp


def _parse_ratio(spec: str) -> dict[str, int]:
    """"하:2,중:5,상:3" -> {"하": 2, "중": 5, "상": 3}"""
    ratio = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        key, _, weight = part.partition(":")
        ratio[key.strip()] = int(weight.strip())
    return ratio


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chapter", required=True, help="대단원 이름 (예: 미적분1)")
    parser.add_argument("--section", action="append", default=[], help="중단원 이름 (여러 번 지정 가능)")
    parser.add_argument("--subsection", action="append", default=[], help="소단원 이름 (여러 번 지정 가능)")
    parser.add_argument("--type", dest="types", action="append", default=[], help="유형 이름 부분 문자열 (여러 번 지정 가능)")
    parser.add_argument("--tier", dest="tiers", action="append", default=[], help="난이도 단계 이름 (핵심 유형/심화 유형/최고난도 유형)")
    parser.add_argument("--label", dest="labels", action="append", default=[], help="난이도 라벨 (하/중/상 등, NGD 출처 문제에만 있음)")
    parser.add_argument("--kind", dest="kinds", action="append", default=[], help="문제 유형 (객관식/서술형/단답형, 여러 번 지정 가능)")
    parser.add_argument("--tier-ratio", default=None, help='난이도 tier 비율. 예: "핵심 유형:3,심화 유형:5,최고난도 유형:2" (--count와 함께 사용)')
    parser.add_argument("--label-ratio", default=None, help='난이도 label 비율. 예: "하:2,중:5,상:3" (--count와 함께 사용)')
    parser.add_argument("--count", type=int, default=None, help="총 문제 수 (안 주면 조건에 맞는 전부)")
    parser.add_argument("--per-type-count", type=int, default=None, help="유형별 최대 문제 수")
    parser.add_argument("--shuffle", action="store_true", help="무작위로 섞은 뒤 count/per-type-count만큼 자른다")
    parser.add_argument("--seed", type=int, default=None, help="--shuffle/--form 재현용 시드")
    parser.add_argument("--title", default="문제집", help="시험지 제목")
    parser.add_argument("--out", required=True, help="출력 파일 경로 접두어 (확장자 없이) - .html/.hwp가 각각 붙는다")
    parser.add_argument("--show-path", action="store_true", help="각 문제 위에 소단원>유형 경로를 표시한다")
    parser.add_argument("--html-only", action="store_true")
    parser.add_argument("--hwp-only", action="store_true")
    parser.add_argument("--db", default="sqlite:///math_bank.db")

    parser.add_argument("--form", dest="forms", action="append", default=[], help='A형/B형처럼 문제·보기 순서를 다르게 섞은 버전 이름 (여러 번 지정, 예: --form A --form B). 안 주면 원래 순서 그대로 1개만 생성.')
    parser.add_argument("--no-shuffle-problem-order", action="store_true", help="--form 사용 시 문제 순서는 안 섞고 보기 순서만 섞는다")
    parser.add_argument("--no-shuffle-choices", action="store_true", help="--form 사용 시 보기 순서는 안 섞고 문제 순서만 섞는다")
    parser.add_argument("--separate-answer-key", action="store_true", help="정답을 시험지에 안 붙이고 별도 파일(_answers)로 생성한다")

    args = parser.parse_args()

    tier_ratio = _parse_ratio(args.tier_ratio) if args.tier_ratio else None
    label_ratio = _parse_ratio(args.label_ratio) if args.label_ratio else None
    if tier_ratio and label_ratio:
        parser.error("--tier-ratio와 --label-ratio는 동시에 줄 수 없습니다.")
    difficulty_ratio = tier_ratio or label_ratio

    sel = WorksheetSelection(
        chapter=args.chapter,
        sections=args.section,
        subsections=args.subsection,
        type_names=args.types,
        difficulty_tiers=args.tiers,
        difficulty_labels=args.labels,
        question_kinds=args.kinds,
        count=args.count,
        per_type_count=args.per_type_count,
        difficulty_ratio=difficulty_ratio,
        shuffle=args.shuffle,
        seed=args.seed,
    )

    engine = init_db(args.db)
    with Session(engine) as session:
        problems = select_problems(session, sel)
        if not problems:
            print("조건에 맞는 문제가 없습니다.")
            return

        forms = args.forms or [""]  # 빈 이름 하나 = 버전 구분 없이 1개만
        variants = make_variants(
            problems,
            forms,
            shuffle_problem_order=bool(args.forms) and not args.no_shuffle_problem_order,
            shuffle_choices=bool(args.forms) and not args.no_shuffle_choices,
            seed=args.seed,
        )

        include_answer_key = not args.separate_answer_key

        for variant in variants:
            suffix = f"_{variant.name}" if variant.name else ""
            out_prefix = f"{args.out}{suffix}"
            path_labels = [describe_problem_path(p) for p in variant.problems] if args.show_path else None

            if not args.hwp_only:
                html_path = f"{out_prefix}.html"
                save_worksheet_html(
                    variant.problems, args.title, html_path, path_labels,
                    variant.choice_orders, variant.display_answers, include_answer_key,
                )
                print(f"HTML 저장: {html_path} ({len(variant.problems)}문제)")
                if args.separate_answer_key:
                    ans_path = f"{out_prefix}_answers.html"
                    save_answer_key_html(args.title, variant.problems, ans_path, variant.display_answers)
                    print(f"정답지 저장: {ans_path}")

            if not args.html_only:
                hwp_path = f"{out_prefix}.hwp"
                save_worksheet_hwp(
                    variant.problems, args.title, hwp_path, show_path=args.show_path,
                    choice_orders=variant.choice_orders, display_answers=variant.display_answers,
                    include_answer_key=include_answer_key,
                )
                print(f"HWP 저장: {hwp_path} ({len(variant.problems)}문제)")
                if args.separate_answer_key:
                    ans_path = f"{out_prefix}_answers.hwp"
                    save_answer_key_hwp(args.title, variant.problems, ans_path, variant.display_answers)
                    print(f"정답지 저장: {ans_path}")


if __name__ == "__main__":
    main()
