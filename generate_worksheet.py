"""자동 출제(Pillar 3) CLI: 대/중/소단원+유형+난이도 조건으로 문제를 뽑아
HTML 시험지와 HWP 시험지를 동시에 생성한다.

예:
  python generate_worksheet.py --chapter 미적분1 --subsection "도함수의 활용 ⑵" \
      --type "함수의 극대" --count 10 --title "도함수의 활용 소단원 평가" \
      --out worksheets/deriv_app2
"""
from __future__ import annotations
import argparse

from sqlalchemy.orm import Session

from models import init_db
from worksheet_select import WorksheetSelection, select_problems, describe_problem_path
from worksheet_render_html import save_worksheet_html
from worksheet_render_hwp import save_worksheet_hwp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chapter", required=True, help="대단원 이름 (예: 미적분1)")
    parser.add_argument("--section", action="append", default=[], help="중단원 이름 (여러 번 지정 가능)")
    parser.add_argument("--subsection", action="append", default=[], help="소단원 이름 (여러 번 지정 가능)")
    parser.add_argument("--type", dest="types", action="append", default=[], help="유형 이름 부분 문자열 (여러 번 지정 가능)")
    parser.add_argument("--tier", dest="tiers", action="append", default=[], help="난이도 단계 이름 (핵심 유형/심화 유형/최고난도 유형)")
    parser.add_argument("--label", dest="labels", action="append", default=[], help="난이도 라벨 (하/중/상 등, NGD 출처 문제에만 있음)")
    parser.add_argument("--count", type=int, default=None, help="총 문제 수 (안 주면 조건에 맞는 전부)")
    parser.add_argument("--per-type-count", type=int, default=None, help="유형별 최대 문제 수")
    parser.add_argument("--shuffle", action="store_true", help="무작위로 섞은 뒤 count/per-type-count만큼 자른다")
    parser.add_argument("--seed", type=int, default=None, help="--shuffle 재현용 시드")
    parser.add_argument("--title", default="문제집", help="시험지 제목")
    parser.add_argument("--out", required=True, help="출력 파일 경로 접두어 (확장자 없이) - .html/.hwp가 각각 붙는다")
    parser.add_argument("--show-path", action="store_true", help="각 문제 위에 소단원>유형 경로를 표시한다")
    parser.add_argument("--html-only", action="store_true")
    parser.add_argument("--hwp-only", action="store_true")
    parser.add_argument("--db", default="sqlite:///math_bank.db")
    args = parser.parse_args()

    sel = WorksheetSelection(
        chapter=args.chapter,
        sections=args.section,
        subsections=args.subsection,
        type_names=args.types,
        difficulty_tiers=args.tiers,
        difficulty_labels=args.labels,
        count=args.count,
        per_type_count=args.per_type_count,
        shuffle=args.shuffle,
        seed=args.seed,
    )

    engine = init_db(args.db)
    with Session(engine) as session:
        problems = select_problems(session, sel)
        if not problems:
            print("조건에 맞는 문제가 없습니다.")
            return

        path_labels = [describe_problem_path(p) for p in problems] if args.show_path else None

        if not args.hwp_only:
            html_path = f"{args.out}.html"
            save_worksheet_html(problems, args.title, html_path, path_labels)
            print(f"HTML 저장: {html_path} ({len(problems)}문제)")

        if not args.html_only:
            hwp_path = f"{args.out}.hwp"
            save_worksheet_hwp(problems, args.title, hwp_path, show_path=args.show_path)
            print(f"HWP 저장: {hwp_path} ({len(problems)}문제)")


if __name__ == "__main__":
    main()
