"""선별된 문제 목록을 인쇄/열람 가능한 HTML 시험지+정답지로 렌더링한다.
수식은 MathJax(CDN)로 $...$ 그대로 렌더링, 이미지 문제는 <img>로 그대로 삽입."""
from __future__ import annotations
import base64
import json
from pathlib import Path

from models import Problem
from text_normalize import strip_watermark_noise

_CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧']


def _img_data_uri(path: str) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    ext = p.suffix.lstrip('.').lower() or 'png'
    b64 = base64.b64encode(p.read_bytes()).decode('ascii')
    return f"data:image/{ext};base64,{b64}"


def _problem_body_html(p: Problem) -> str:
    parts = []
    if p.image_paths:
        for path in json.loads(p.image_paths):
            uri = _img_data_uri(path)
            if uri:
                parts.append(f'<img src="{uri}" alt="문제 이미지">')
    elif p.stem_latex:
        text = strip_watermark_noise(p.stem_latex).replace('\n', '<br>')
        parts.append(f'<div class="stem-text">{text}</div>')
        if p.choices_latex:
            try:
                choices = json.loads(p.choices_latex)
            except (json.JSONDecodeError, TypeError):
                choices = None
            if choices:
                items = ''.join(
                    f'<span class="choice">{_CIRCLED[i] if i < len(_CIRCLED) else i+1} {strip_watermark_noise(c)}</span>'
                    for i, c in enumerate(choices)
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
  .choices {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px 22px; }}
  img {{ max-width: 100%; display: block; margin-top: 6px; }}
  .answer-key {{ margin-top: 60px; border-top: 2px solid #333; padding-top: 16px; }}
  .answer-key table {{ border-collapse: collapse; width: 100%; font-size: 0.9em; }}
  .answer-key td, .answer-key th {{ border: 1px solid #ccc; padding: 4px 8px; text-align: center; }}
  @media print {{ .problem {{ break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
<div class="answer-key">
<h2>정답</h2>
<table>
<tr>{answer_header}</tr>
<tr>{answer_row}</tr>
</table>
</div>
</body>
</html>
"""


def render_worksheet_html(problems: list[Problem], title: str, path_labels: list[str] | None = None) -> str:
    """문제 목록을 자체완결 HTML 문자열로 렌더링한다 (파일 경로 이미지는 base64로 임베드)."""
    blocks = []
    for i, p in enumerate(problems, start=1):
        path_line = f'<div class="path">{path_labels[i-1]}</div>' if path_labels else ''
        blocks.append(
            f'<div class="problem"><span class="num">{i}.</span>{path_line}{_problem_body_html(p)}</div>'
        )
    header_cells = ''.join(f'<th>{i}</th>' for i in range(1, len(problems) + 1))
    answer_cells = ''.join(f'<td>{p.answer or "-"}</td>' for p in problems)
    return _PAGE_TEMPLATE.format(
        title=title, body='\n'.join(blocks), answer_header=header_cells, answer_row=answer_cells
    )


def save_worksheet_html(problems: list[Problem], title: str, out_path: str, path_labels: list[str] | None = None) -> None:
    html = render_worksheet_html(problems, title, path_labels)
    Path(out_path).write_text(html, encoding='utf-8')
