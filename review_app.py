"""
쎈수학 자동 크롭 중 확신이 안 서는 것만(needs_review=True) 사람이 눈으로
보고 마우스로 다시 영역을 지정하는 로컬 검토 도구.

실행: python review_app.py
브라우저: http://127.0.0.1:5057
"""
from __future__ import annotations

import io
import json

import fitz
from flask import Flask, jsonify, request, send_file, Response
from sqlalchemy.orm import Session

from models import Problem, ProblemType, SubSection, Section, Chapter, Source, init_db
from pdf_sen_extract import _save_trimmed

app = Flask(__name__)
engine = init_db()

DISPLAY_DPI = 130   # 브라우저에 보여주는 페이지 이미지 해상도
SAVE_DPI = 200       # 실제 저장할 크롭 해상도(기존 파이프라인과 동일)


def _problem_context(session: Session, p: Problem) -> dict:
    ptype = session.get(ProblemType, p.problem_type_id)
    sub = session.get(SubSection, ptype.subsection_id) if ptype else None
    sec = session.get(Section, sub.section_id) if sub else None
    chapter = session.get(Chapter, sec.chapter_id) if sec else None
    return {
        'id': p.id,
        'type_name': ptype.name if ptype else '',
        'type_code': ptype.code if ptype else '',
        'subsection': sub.name if sub else '',
        'subject': chapter.name if chapter else '',
        'answer': p.answer,
        'page_index': p.source_page_index,
        'pdf_path': p.original_file_path,
        'image_path': json.loads(p.image_paths)[0] if p.image_paths else None,
    }


@app.route('/')
def index():
    with Session(engine) as s:
        rows = (
            s.query(Chapter.name, Problem.id)
            .join(Section, Section.chapter_id == Chapter.id)
            .join(SubSection, SubSection.section_id == Section.id)
            .join(ProblemType, ProblemType.subsection_id == SubSection.id)
            .join(Problem, Problem.problem_type_id == ProblemType.id)
            .filter(Problem.needs_review.is_(True))
            .all()
        )
    counts: dict[str, int] = {}
    for name, _ in rows:
        counts[name] = counts.get(name, 0) + 1
    total = len(rows)
    items = ''.join(
        f'<li><a href="/review/{name}">{name}</a> — {n}개</li>'
        for name, n in sorted(counts.items())
    )
    return f'''
    <html><head><meta charset="utf-8"><title>쎈수학 크롭 검토</title>
    <style>body{{font-family:sans-serif;max-width:600px;margin:40px auto}}</style></head>
    <body>
    <h2>검토 대상: 총 {total}개</h2>
    <ul>{items}</ul>
    </body></html>
    '''


@app.route('/review/<subject>')
def review_subject(subject):
    with Session(engine) as s:
        chapter = s.query(Chapter).filter_by(name=subject).one_or_none()
        if chapter is None:
            return f'과목 없음: {subject}', 404
        row = (
            s.query(Problem.id)
            .join(ProblemType, Problem.problem_type_id == ProblemType.id)
            .join(SubSection, ProblemType.subsection_id == SubSection.id)
            .join(Section, SubSection.section_id == Section.id)
            .filter(Section.chapter_id == chapter.id, Problem.needs_review.is_(True))
            .order_by(Problem.id)
            .first()
        )
    if row is None:
        return f'<h2>{subject}: 검토할 항목이 없어요. 끝!</h2><a href="/">목록으로</a>'
    return _render_review_page(row[0])


def _render_review_page(problem_id: int) -> str:
    with Session(engine) as s:
        p = s.get(Problem, problem_id)
        if p is None:
            return '문제 없음', 404
        ctx = _problem_context(s, p)

    return f'''
    <html><head><meta charset="utf-8"><title>검토 {problem_id}</title>
    <style>
      body {{ font-family: sans-serif; margin: 20px; }}
      #wrap {{ display: flex; gap: 20px; }}
      #pageBox {{ position: relative; border: 1px solid #ccc; }}
      #pageImg {{ display: block; max-width: 900px; }}
      #selBox {{ position: absolute; border: 2px solid red; background: rgba(255,0,0,0.1); display:none; }}
      #side {{ width: 320px; }}
      #currentImg {{ max-width: 300px; border: 1px solid #ccc; }}
      button {{ padding: 8px 16px; margin: 4px 4px 4px 0; font-size: 14px; }}
      .info {{ font-size: 13px; color: #444; line-height: 1.6; }}
    </style></head>
    <body>
    <h3>#{problem_id} — {ctx['subject']} &gt; {ctx['subsection']} &gt; {ctx['type_name']}</h3>
    <p class="info">
      정답: {ctx['answer']} · 원본 페이지: {ctx['page_index']}<br>
      페이지 위에서 마우스로 드래그해서 문제 영역을 다시 지정하세요. 지금 크롭이 맞으면 "이대로 승인"을 누르세요.
    </p>
    <div id="wrap">
      <div id="pageBox">
        <img id="pageImg" src="/api/page_image/{problem_id}">
        <div id="selBox"></div>
      </div>
      <div id="side">
        <h4>현재 저장된 크롭</h4>
        <img id="currentImg" src="/api/current_image/{problem_id}?t={problem_id}">
        <div>
          <button onclick="saveSelection()">이 영역으로 저장</button><br>
          <button onclick="approve()">이대로 승인</button><br>
          <button onclick="location.href='/review/{ctx['subject']}'">건너뛰기(다음)</button>
        </div>
      </div>
    </div>
    <script>
      const problemId = {problem_id};
      const subject = {json.dumps(ctx['subject'])};
      const img = document.getElementById('pageImg');
      const box = document.getElementById('pageBox');
      const sel = document.getElementById('selBox');
      let start = null, rect = null;

      box.addEventListener('mousedown', e => {{
        const r = img.getBoundingClientRect();
        start = {{x: e.clientX - r.left, y: e.clientY - r.top}};
        sel.style.display = 'block';
      }});
      box.addEventListener('mousemove', e => {{
        if (!start) return;
        const r = img.getBoundingClientRect();
        const x = e.clientX - r.left, y = e.clientY - r.top;
        const x0 = Math.min(start.x, x), y0 = Math.min(start.y, y);
        const w = Math.abs(x - start.x), h = Math.abs(y - start.y);
        sel.style.left = x0 + 'px'; sel.style.top = y0 + 'px';
        sel.style.width = w + 'px'; sel.style.height = h + 'px';
        rect = {{x0, y0, x1: x0 + w, y1: y0 + h}};
      }});
      box.addEventListener('mouseup', () => {{ start = null; }});

      function afterSave() {{
        location.href = '/review/' + subject;
      }}
      function saveSelection() {{
        if (!rect || rect.x1 - rect.x0 < 5) {{ alert('영역을 먼저 드래그로 지정하세요.'); return; }}
        const naturalScale = img.naturalWidth / img.clientWidth;
        const payload = {{
          x0: rect.x0 * naturalScale, y0: rect.y0 * naturalScale,
          x1: rect.x1 * naturalScale, y1: rect.y1 * naturalScale,
        }};
        fetch('/api/save/' + problemId, {{
          method: 'POST', headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(payload),
        }}).then(r => r.json()).then(afterSave);
      }}
      function approve() {{
        fetch('/api/approve/' + problemId, {{method: 'POST'}}).then(r => r.json()).then(afterSave);
      }}
    </script>
    </body></html>
    '''


@app.route('/api/page_image/<int:problem_id>')
def page_image(problem_id):
    with Session(engine) as s:
        p = s.get(Problem, problem_id)
        if p is None or p.original_file_path is None or p.source_page_index is None:
            return '페이지 정보 없음', 404
        pdf_path, page_index = p.original_file_path, p.source_page_index
    doc = fitz.open(pdf_path)
    pix = doc[page_index].get_pixmap(dpi=DISPLAY_DPI)
    doc.close()
    return Response(pix.tobytes('png'), mimetype='image/png')


@app.route('/api/current_image/<int:problem_id>')
def current_image(problem_id):
    with Session(engine) as s:
        p = s.get(Problem, problem_id)
        if p is None:
            return '없음', 404
        image_path = json.loads(p.image_paths)[0]
    return send_file(image_path, mimetype='image/png')


@app.route('/api/approve/<int:problem_id>', methods=['POST'])
def approve(problem_id):
    with Session(engine) as s:
        p = s.get(Problem, problem_id)
        if p is None:
            return jsonify(ok=False), 404
        p.needs_review = False
        s.commit()
    return jsonify(ok=True)


@app.route('/api/save/<int:problem_id>', methods=['POST'])
def save(problem_id):
    data = request.get_json()
    with Session(engine) as s:
        p = s.get(Problem, problem_id)
        if p is None or p.original_file_path is None or p.source_page_index is None:
            return jsonify(ok=False, error='페이지 정보 없음'), 404
        image_path = json.loads(p.image_paths)[0]
        pdf_path, page_index = p.original_file_path, p.source_page_index

        doc = fitz.open(pdf_path)
        page = doc[page_index]
        # 브라우저 표시 픽셀(DISPLAY_DPI 기준) -> PDF 포인트 -> 저장용 DPI로 재렌더
        x0 = data['x0'] * 72 / DISPLAY_DPI
        y0 = data['y0'] * 72 / DISPLAY_DPI
        x1 = data['x1'] * 72 / DISPLAY_DPI
        y1 = data['y1'] * 72 / DISPLAY_DPI
        clip = fitz.Rect(x0, y0, x1, y1)
        pix = page.get_pixmap(clip=clip, dpi=SAVE_DPI)
        doc.close()

        _save_trimmed(pix, image_path, bottom_pad=10, min_height=30)
        p.needs_review = False
        s.commit()
    return jsonify(ok=True)


if __name__ == '__main__':
    with Session(engine) as s:
        n = s.query(Problem).filter_by(needs_review=True).count()
    print(f'검토 대상: {n}개')
    print('http://127.0.0.1:5057 에서 열어보세요')
    app.run(port=5057, debug=False)
