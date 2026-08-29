"""선별된 문제 목록을 인쇄/열람 가능한 HTML 시험지+정답지로 렌더링한다.
수식은 MathJax(CDN)로 $...$ 그대로 렌더링, 이미지 문제는 <img>로 그대로 삽입."""
from __future__ import annotations
import base64
import json
from pathlib import Path

from models import Problem
from text_normalize import strip_watermark_noise
from condition_box import split_condition_block

_CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧']


def _img_data_uri(path: str) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    ext = p.suffix.lstrip('.').lower() or 'png'
    b64 = base64.b64encode(p.read_bytes()).decode('ascii')
    return f"data:image/{ext};base64,{b64}"


def _problem_body_html(p: Problem, choice_order: list[int] | None) -> str:
    parts = []
    if p.image_paths:
        for path in json.loads(p.image_paths):
            uri = _img_data_uri(path)
            if uri:
                parts.append(f'<img src="{uri}" alt="문제 이미지">')
    elif p.stem_latex:
        stem = strip_watermark_noise(p.stem_latex)
        main_text, condition_items, trailing_text = split_condition_block(stem)
        parts.append(f'<div class="stem-text">{main_text.replace(chr(10), "<br>")}</div>')
        if condition_items:
            lines = ''.join(f'<div>{item.replace(chr(10), "<br>")}</div>' for item in condition_items)
            parts.append(f'<div class="condition-box">{lines}</div>')
            if trailing_text:
                parts.append(f'<div class="stem-text">{trailing_text.replace(chr(10), "<br>")}</div>')
        if p.choices_latex:
            try:
                choices = json.loads(p.choices_latex)
            except (json.JSONDecodeError, TypeError):
                choices = None
            if choices:
                order = choice_order if choice_order is not None else list(range(len(choices)))
                items = ''.join(
                    f'<span class="choice">{_CIRCLED[i] if i < len(_CIRCLED) else i+1} {strip_watermark_noise(choices[orig_i])}</span>'
                    for i, orig_i in enumerate(order)
                )
                parts.append(f'<div class="choices">{items}</div>')
    return '\n'.join(parts)


_PAGE_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title}</title>
<script>
window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" defer></script>
<style>
  body {{ font-family: "맑은 고딕", sans-serif; max-width: 820px; margin: 40px auto; line-height: 1.7; }}
  h1 {{ font-size: 1.4em; border-bottom: 2px solid #333; padding-bottom: 8px; }}
  .problem {{ margin: 28px 0; page-break-inside: avoid; }}
  .problem .num {{ font-weight: bold; margin-right: 6px; }}
  .path {{ color: #888; font-size: 0.78em; margin-bottom: 4px; }}
  .stem-text {{ margin-top: 4px; }}
  .condition-box {{ margin-top: 8px; border: 1px solid #333; padding: 10px 14px; }}
  .condition-box div {{ margin: 2px 0; }}
  .choices {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px 22px; }}
  img {{ max-width: 100%; display: block; margin-top: 6px; }}
  .answer-key {{ margin-top: 60px; border-top: 2px solid #333; padding-top: 16px; }}
  .answer-key table {{ border-collapse: collapse; width: 100%; font-size: 0.9em; }}
  .answer-key td, .answer-key th {{ border: 1px solid #ccc; padding: 4px 8px; text-align: center; }}
  .explanation-key {{ margin-top: 30px; }}
  .explanation-key .item {{ margin: 14px 0; }}
  .explanation-key .num {{ font-weight: bold; margin-right: 6px; }}
  @media print {{ .problem {{ break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
{answer_section}
</body>
</html>
"""

_ANSWER_SECTION_TEMPLATE = """<div class="answer-key">
<h2>정답</h2>
<table>
<tr>{answer_header}</tr>
<tr>{answer_row}</tr>
</table>
</div>"""


def _answer_section_html(problems: list[Problem], display_answers: list[str | None] | None) -> str:
    header_cells = ''.join(f'<th>{i}</th>' for i in range(1, len(problems) + 1))
    if display_answers is None:
        display_answers = [p.answer for p in problems]
    answer_cells = ''.join(f'<td>{a or "-"}</td>' for a in display_answers)
    return _ANSWER_SECTION_TEMPLATE.format(answer_header=header_cells, answer_row=answer_cells)


def _explanation_section_html(problems: list[Problem]) -> str:
    """해설이 있는 문제만 번호와 함께 나열한다 (없는 문제는 조용히 건너뜀 -
    이 DB는 아직 모든 문제에 해설이 있는 게 아니라서)."""
    items = ''.join(
        f'<div class="item"><span class="num">{i}.</span>{strip_watermark_noise(p.explanation).replace(chr(10), "<br>")}</div>'
        for i, p in enumerate(problems, start=1)
        if p.explanation
    )
    if not items:
        return ''
    return f'<div class="explanation-key"><h2>해설</h2>{items}</div>'


def render_worksheet_html(
    problems: list[Problem],
    title: str,
    path_labels: list[str] | None = None,
    choice_orders: list[list[int] | None] | None = None,
    display_answers: list[str | None] | None = None,
    include_answer_key: bool = True,
    include_explanations: bool = False,
) -> str:
    """문제 목록을 자체완결 HTML 문자열로 렌더링한다 (파일 경로 이미지는 base64로 임베드).
    choice_orders/display_answers를 주면 A형/B형처럼 보기 순서가 섞인 버전을 그대로 반영한다."""
    blocks = []
    for i, p in enumerate(problems, start=1):
        path_line = f'<div class="path">{path_labels[i-1]}</div>' if path_labels else ''
        order = choice_orders[i - 1] if choice_orders else None
        blocks.append(
            f'<div class="problem"><span class="num">{i}.</span>{path_line}{_problem_body_html(p, order)}</div>'
        )
    answer_section = _answer_section_html(problems, display_answers) if include_answer_key else ''
    if include_answer_key and include_explanations:
        answer_section += _explanation_section_html(problems)
    return _PAGE_TEMPLATE.format(title=title, body='\n'.join(blocks), answer_section=answer_section)


def render_answer_key_html(
    title: str,
    problems: list[Problem],
    display_answers: list[str | None] | None = None,
    include_explanations: bool = False,
) -> str:
    """정답만 담은 별도 HTML(정답지)을 렌더링한다."""
    body = f'<h1>{title} - 정답</h1>\n' + _answer_section_html(problems, display_answers)
    if include_explanations:
        body += _explanation_section_html(problems)
    return f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{title} 정답</title></head><body>{body}</body></html>'


def save_worksheet_html(
    problems: list[Problem],
    title: str,
    out_path: str,
    path_labels: list[str] | None = None,
    choice_orders: list[list[int] | None] | None = None,
    display_answers: list[str | None] | None = None,
    include_answer_key: bool = True,
    include_explanations: bool = False,
) -> None:
    html = render_worksheet_html(
        problems, title, path_labels, choice_orders, display_answers, include_answer_key, include_explanations
    )
    Path(out_path).write_text(html, encoding='utf-8')


def save_answer_key_html(
    title: str,
    problems: list[Problem],
    out_path: str,
    display_answers: list[str | None] | None = None,
    include_explanations: bool = False,
) -> None:
    html = render_answer_key_html(title, problems, display_answers, include_explanations)
    Path(out_path).write_text(html, encoding='utf-8')
