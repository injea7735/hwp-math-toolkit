"""
로컬 시험지 생성 + 자료 업로드 웹앱. 터미널에서 generate_worksheet.py를
직접 실행하는 대신, 브라우저에서 단원을 고르고 반복적으로 시험지를 뽑을 수
있게 한다. 새 HWP/PDF 자료도 업로드해서 이미 검증된 기존 파이프라인으로
바로 DB에 넣을 수 있다(형식/과목은 사람이 고르고, 추출만 자동 - 이 화면은
자동 형식 감지를 하지 않는다. 지금까지 다뤄본 적 없는 새 자료 형식은 여기서
처리할 수 없고 별도 세션에서 파서를 새로 만들어야 한다).

실행: python worksheet_app.py
브라우저: http://127.0.0.1:5058
"""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from sqlalchemy.orm import Session
from werkzeug.utils import secure_filename

import import_pdf_problems
import import_workbook_outline
import import_workbook_problems
import link_pdf_answers
import link_pdf_explanations
import pdf_problem_extract
from generate_worksheet import _parse_ratio
from models import init_db
from taxonomy_tree import (
    distinct_difficulty_labels,
    distinct_question_kinds,
    list_chapters,
    list_difficulty_tiers,
    list_sections,
    list_subsections,
    list_types,
)
from worksheet_render_hwp import save_answer_key_hwp, save_worksheet_hwp
from worksheet_render_html import save_answer_key_html, save_worksheet_html
from worksheet_select import WorksheetSelection, describe_problem_path, select_problems
from worksheet_variants import make_variants

app = Flask(__name__)
engine = init_db()

# HWP-COM 자동화는 동시에 여러 요청에서 겹치면 안 되는 동기 작업이라 직렬화한다.
# Flask 개발 서버는 threaded=True를 안 주면 어차피 한 번에 한 요청만 처리하므로
# 지금은 이 락이 사실상 무의미하지만, 나중에 HTML 전용 경로만 threaded로
# 바꾸는 등의 변경이 생겨도 안전하도록 방어적으로 남겨둔다.
_hwp_lock = threading.Lock()

WORKSHEETS_DIR = Path("worksheets")
UPLOADS_DIR = Path("uploads")
WORKSHEETS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)


# 이 화면에서 재실행 가능한 파이프라인만 등록한다 - "파일 경로 하나를 받아
# 그대로 새로 돌릴 수 있는" 것들만이다. 아래는 의도적으로 제외:
#   - backfill_gongtong_difficulty.py / link_gongtong_explanations.py:
#     고정된 18개 파일 목록(FILES 상수)에 하드코딩돼 있어 새 업로드 파일에 못 씀
#   - backfill_review_flags.py, repair_*.py: 특정 과거 사고 복구용 일회성 스크립트
#   - import_rpm_problems.py / import_sumaessing_problems.py /
#     import_mi1_sen_problems.py / import_geo_sen_types.py 등: SUBJECT가
#     코드에 고정돼 있고, raw 경로가 아니라 이미 파싱된 리스트를 받는
#     insert_* 함수라서 스크립트별로 extract_* 시그니처를 따로 확인해야 함 -
#     1차 구현에서는 제외, 필요해지면 하나씩 추가한다.
PIPELINES = {
    "유형서 HWP (대/중/소단원+유형 전체 등록)": {
        "steps": ["outline", "problems"],
        "file_ext": ".hwp",
        "extra_fields": ["unit_title_override"],
    },
    "PDF 문제 (내신고쟁이류, 커스텀 폰트 글리프형)": {
        "steps": ["pdf_problems"],
        "file_ext": ".pdf",
        "extra_fields": ["image_out_dir", "section_names_csv"],
    },
    "PDF 정답 연결 (해설 PDF)": {
        "steps": ["link_answers"],
        "file_ext": ".pdf",
        "extra_fields": [],
    },
    "PDF 해설 연결 (해설 PDF)": {
        "steps": ["link_explanations"],
        "file_ext": ".pdf",
        "extra_fields": [],
    },
}


def _selection_from_body(body: dict) -> WorksheetSelection:
    ratio = _parse_ratio(body["ratio"]) if body.get("ratio") else None
    return WorksheetSelection(
        chapter=body.get("chapter") or "",
        sections=body.get("sections") or [],
        subsections=body.get("subsections") or [],
        type_names=body.get("type_names") or [],
        difficulty_tiers=body.get("difficulty_tiers") or [],
        difficulty_labels=body.get("difficulty_labels") or [],
        question_kinds=body.get("question_kinds") or [],
        count=body.get("count"),
        per_type_count=body.get("per_type_count"),
        difficulty_ratio=ratio,
        shuffle=bool(body.get("shuffle")),
        seed=body.get("seed"),
    )


# ---------------------------------------------------------------- Feature A


@app.route("/")
def index():
    return MAIN_PAGE_HTML


@app.route("/api/chapters")
def api_chapters():
    with Session(engine) as s:
        return jsonify(list_chapters(s))


@app.route("/api/sections")
def api_sections():
    chapter = request.args.get("chapter", "")
    with Session(engine) as s:
        return jsonify(list_sections(s, chapter))


@app.route("/api/subsections")
def api_subsections():
    chapter = request.args.get("chapter", "")
    sections = request.args.getlist("section")
    with Session(engine) as s:
        return jsonify(list_subsections(s, chapter, sections or None))


@app.route("/api/types")
def api_types():
    chapter = request.args.get("chapter", "")
    sections = request.args.getlist("section")
    subsections = request.args.getlist("subsection")
    with Session(engine) as s:
        return jsonify(list_types(s, chapter, sections or None, subsections or None))


@app.route("/api/difficulty_options")
def api_difficulty_options():
    chapter = request.args.get("chapter", "")
    with Session(engine) as s:
        return jsonify({
            "tiers": list_difficulty_tiers(s),
            "labels": distinct_difficulty_labels(s, chapter),
            "kinds": distinct_question_kinds(s, chapter),
        })


@app.route("/api/preview_count", methods=["POST"])
def api_preview_count():
    body = request.get_json(force=True)
    if not body.get("chapter"):
        return jsonify(count=0)
    sel = _selection_from_body(body)
    with Session(engine) as s:
        problems = select_problems(s, sel)
    return jsonify(count=len(problems))


@app.route("/api/generate", methods=["POST"])
def api_generate():
    body = request.get_json(force=True)
    if not body.get("chapter"):
        return jsonify(ok=False, error="대단원을 선택하세요"), 400

    sel = _selection_from_body(body)
    title = body.get("title") or "문제집"
    forms = [f for f in (body.get("forms") or []) if f] or [""]
    shuffle_problem_order = bool(body.get("shuffle_problem_order"))
    shuffle_choices = bool(body.get("shuffle_choices"))
    separate_answer_key = bool(body.get("separate_answer_key"))
    with_explanation = bool(body.get("with_explanation"))
    show_path = bool(body.get("show_path"))
    formats = body.get("formats") or ["html"]

    with Session(engine) as session:
        problems = select_problems(session, sel)
        if not problems:
            return jsonify(ok=False, error="조건에 맞는 문제가 없습니다"), 400

        variants = make_variants(problems, forms, shuffle_problem_order, shuffle_choices, sel.seed)
        include_answer_key = not separate_answer_key

        run_id = uuid.uuid4().hex[:8]
        out_dir = WORKSHEETS_DIR / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        files: list[str] = []

        for variant in variants:
            suffix = f"_{variant.name}" if variant.name else ""
            out_prefix = out_dir / f"worksheet{suffix}"
            path_labels = [describe_problem_path(p) for p in variant.problems] if show_path else None

            if "html" in formats:
                html_path = out_prefix.with_suffix(".html")
                save_worksheet_html(
                    variant.problems, title, str(html_path), path_labels,
                    variant.choice_orders, variant.display_answers, include_answer_key,
                    with_explanation,
                )
                files.append(html_path.name)
                if separate_answer_key:
                    ans_path = out_dir / f"worksheet{suffix}_answers.html"
                    save_answer_key_html(
                        title, variant.problems, str(ans_path), variant.display_answers, with_explanation,
                    )
                    files.append(ans_path.name)

            if "hwp" in formats:
                hwp_path = out_prefix.with_suffix(".hwp")
                with _hwp_lock:
                    save_worksheet_hwp(
                        variant.problems, title, str(hwp_path), show_path=show_path,
                        choice_orders=variant.choice_orders, display_answers=variant.display_answers,
                        include_answer_key=include_answer_key, include_explanations=with_explanation,
                    )
                files.append(hwp_path.name)
                if separate_answer_key:
                    ans_path = out_dir / f"worksheet{suffix}_answers.hwp"
                    with _hwp_lock:
                        save_answer_key_hwp(
                            title, variant.problems, str(ans_path), variant.display_answers, with_explanation,
                        )
                    files.append(ans_path.name)

    return jsonify(ok=True, run_id=run_id, count=len(problems), files=files)


@app.route("/api/download/<run_id>/<filename>")
def api_download(run_id, filename):
    base = (WORKSHEETS_DIR / run_id).resolve()
    target = (WORKSHEETS_DIR / run_id / filename).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return "잘못된 경로", 400
    if not target.is_file():
        return "파일 없음", 404
    return send_file(target, as_attachment=True)


# ---------------------------------------------------------------- Feature B


@app.route("/upload")
def upload_page():
    return UPLOAD_PAGE_HTML


@app.route("/api/pipelines")
def api_pipelines():
    return jsonify(PIPELINES)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    pipeline_key = request.form.get("pipeline", "")
    subject = (request.form.get("subject") or "").strip()
    pipeline = PIPELINES.get(pipeline_key)
    if pipeline is None:
        return jsonify(ok=False, error="알 수 없는 파이프라인입니다"), 400
    if not subject:
        return jsonify(ok=False, error="과목(대단원 이름)을 입력하세요"), 400

    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify(ok=False, error="파일을 선택하세요"), 400
    if not file.filename.lower().endswith(pipeline["file_ext"]):
        return jsonify(ok=False, error=f"이 파이프라인은 {pipeline['file_ext']} 파일이어야 합니다"), 400

    safe_name = secure_filename(file.filename)
    dest = UPLOADS_DIR / f"{int(time.time())}_{safe_name}"
    file.save(str(dest))
    path = str(dest)

    unit_title_override = (request.form.get("unit_title_override") or "").strip() or None
    image_out_dir = (request.form.get("image_out_dir") or "").strip() or f"problem_images/{subject}"
    section_names = [
        s.strip() for s in (request.form.get("section_names_csv") or "").split(",") if s.strip()
    ]

    results: list[dict] = []
    try:
        with Session(engine) as session:
            for step in pipeline["steps"]:
                if step == "outline":
                    created = import_workbook_outline.import_outline_file(
                        session, subject, path, unit_title_override,
                    )
                    session.commit()  # 바로 다음 problems 스텝이 이 유형을 조회해야 함
                    results.append({"step": "단원/유형 등록", "created": created})
                elif step == "problems":
                    created, skipped = import_workbook_problems.import_problems_file(
                        session, subject, path, unit_title_override,
                    )
                    results.append({"step": "문제 등록", "created": created, "유형없어 건너뜀": skipped})
                elif step == "pdf_problems":
                    if not section_names:
                        raise ValueError("대단원 이름을 콤마로 구분해서 입력하세요")
                    parsed = pdf_problem_extract.extract_problems(path, image_out_dir, len(section_names))
                    created = import_pdf_problems.insert_pdf_problems(
                        session, subject, section_names, parsed, path,
                    )
                    results.append({"step": "PDF 문제 등록", "created": created})
                elif step == "link_answers":
                    updated, missing = link_pdf_answers.link_answers(session, subject, path)
                    results.append({"step": "정답 연결", "updated": updated, "missing": missing})
                elif step == "link_explanations":
                    updated, missing = link_pdf_explanations.link_explanations(session, subject, path)
                    results.append({"step": "해설 연결", "updated": updated, "missing": missing})
            session.commit()
    except Exception as e:
        return jsonify(ok=False, error=str(e), results=results), 500

    return jsonify(ok=True, results=results, uploaded_path=path)


# ---------------------------------------------------------------- HTML/JS


MAIN_PAGE_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>시험지 생성</title>
<style>
body{font-family:sans-serif;max-width:900px;margin:30px auto;line-height:1.6}
fieldset{margin-bottom:16px;padding:10px 14px}
label{display:inline-block;margin-right:14px;margin-bottom:4px}
.checkbox-list{display:flex;flex-wrap:wrap;gap:4px 14px;max-height:150px;overflow-y:auto;border:1px solid #ddd;padding:8px;margin:4px 0 10px}
#count-preview{font-weight:bold;color:#0a6}
button{padding:8px 16px;font-size:14px;cursor:pointer}
#result{margin-top:16px}
a.dl{display:block;margin:2px 0}
nav{margin-bottom:16px}
nav a{margin-right:12px}
</style></head>
<body>
<nav><a href="/">시험지 생성</a> &middot; <a href="/upload">자료 업로드</a></nav>
<h2>시험지 생성</h2>

<fieldset>
<legend>단원</legend>
<label>대단원 <select id="chapter"><option value="">-- 선택 --</option></select></label>
<div>중단원 <div id="sections" class="checkbox-list"></div></div>
<div>소단원 <div id="subsections" class="checkbox-list"></div></div>
<div>유형 <div id="types" class="checkbox-list"></div></div>
</fieldset>

<fieldset>
<legend>난이도 / 문제 유형</legend>
<div>난이도 단계 <div id="tiers" class="checkbox-list"></div></div>
<div>난이도 라벨 <div id="labels" class="checkbox-list"></div></div>
<div>문제 유형(객관식/서술형 등) <div id="kinds" class="checkbox-list"></div></div>
<label>난이도 비율 (예: 하:2,중:5,상:3 - 총 문제 수와 함께 사용) <input id="ratio" size="30"></label>
</fieldset>

<fieldset>
<legend>출제 옵션</legend>
<label>총 문제 수 <input id="count" type="number" min="1"></label>
<label>유형별 최대 문제 수 <input id="perType" type="number" min="1"></label>
<label><input id="shuffle" type="checkbox"> 무작위로 문제 선택(개수 제한 시)</label>
<label>시드 <input id="seed" type="number" placeholder="비우면 매번 랜덤"></label>
</fieldset>

<fieldset>
<legend>출력</legend>
<label>제목 <input id="title" value="문제집" size="30"></label><br>
<label>버전 이름(A형/B형처럼, 콤마구분 - 비우면 1개만) <input id="forms" size="20" placeholder="예: A,B"></label><br>
<label><input id="shuffleProblemOrder" type="checkbox" checked> 버전별 문제 순서 섞기</label>
<label><input id="shuffleChoices" type="checkbox" checked> 버전별 보기 순서 섞기</label>
<label><input id="showPath" type="checkbox"> 문제 위에 경로 표시</label><br>
<label><input id="separateAnswer" type="checkbox"> 정답지 분리 생성</label>
<label><input id="withExplanation" type="checkbox"> 해설 포함</label><br>
<label><input type="checkbox" class="fmt" value="html" checked> HTML</label>
<label><input type="checkbox" class="fmt" value="hwp" checked> HWP</label>
</fieldset>

<p>조건에 맞는 문제: <span id="count-preview">-</span>개</p>
<button id="genBtn" onclick="generate()">시험지 생성</button>
<div id="result"></div>

<script>
function esc(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function currentChecked(containerId) {
  return Array.from(document.querySelectorAll('#' + containerId + ' input:checked')).map(cb => cb.value);
}

function renderCheckboxList(containerId, names, countsMap, onChange) {
  const el = document.getElementById(containerId);
  el.innerHTML = names.map(name => {
    const label = countsMap && (name in countsMap) ? `${esc(name)} (${countsMap[name]})` : esc(name);
    return `<label><input type="checkbox" value="${esc(name)}"> ${label}</label>`;
  }).join('');
  el.querySelectorAll('input[type=checkbox]').forEach(cb => cb.addEventListener('change', onChange));
}

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  return r.json();
}

function qs(params) {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach(x => usp.append(k, x));
    else if (v) usp.append(k, v);
  }
  return usp.toString();
}

async function loadChapters() {
  const chapters = await fetchJSON('/api/chapters');
  const sel = document.getElementById('chapter');
  sel.innerHTML = '<option value="">-- 선택 --</option>' +
    chapters.map(c => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join('');
  sel.addEventListener('change', onChapterChange);
}

async function onChapterChange() {
  await refreshSections();
  await refreshDifficultyOptions();
  await refreshSubsections();
  await refreshTypes();
  schedulePreview();
}

async function refreshSections() {
  const chapter = document.getElementById('chapter').value;
  const items = chapter ? await fetchJSON('/api/sections?' + qs({chapter})) : [];
  renderCheckboxList('sections', items.map(i => i.name), null, onSectionChange);
}

async function onSectionChange() {
  await refreshSubsections();
  await refreshTypes();
  schedulePreview();
}

async function refreshSubsections() {
  const chapter = document.getElementById('chapter').value;
  const sections = currentChecked('sections');
  const items = chapter ? await fetchJSON('/api/subsections?' + qs({chapter, section: sections})) : [];
  renderCheckboxList('subsections', items.map(i => i.name), null, onSubsectionChange);
}

async function onSubsectionChange() {
  await refreshTypes();
  schedulePreview();
}

async function refreshTypes() {
  const chapter = document.getElementById('chapter').value;
  const sections = currentChecked('sections');
  const subsections = currentChecked('subsections');
  const items = chapter ? await fetchJSON('/api/types?' + qs({chapter, section: sections, subsection: subsections})) : [];
  const counts = {};
  items.forEach(i => { counts[i.name] = i.problem_count; });
  renderCheckboxList('types', items.map(i => i.name), counts, schedulePreview);
}

async function refreshDifficultyOptions() {
  const chapter = document.getElementById('chapter').value;
  const data = chapter ? await fetchJSON('/api/difficulty_options?' + qs({chapter})) : {tiers: [], labels: [], kinds: []};
  renderCheckboxList('tiers', data.tiers.map(t => t.name), null, schedulePreview);
  renderCheckboxList('labels', data.labels, null, schedulePreview);
  renderCheckboxList('kinds', data.kinds, null, schedulePreview);
}

function collectSelection() {
  return {
    chapter: document.getElementById('chapter').value,
    sections: currentChecked('sections'),
    subsections: currentChecked('subsections'),
    type_names: currentChecked('types'),
    difficulty_tiers: currentChecked('tiers'),
    difficulty_labels: currentChecked('labels'),
    question_kinds: currentChecked('kinds'),
    count: document.getElementById('count').value ? parseInt(document.getElementById('count').value) : null,
    per_type_count: document.getElementById('perType').value ? parseInt(document.getElementById('perType').value) : null,
    ratio: document.getElementById('ratio').value || null,
    shuffle: document.getElementById('shuffle').checked,
    seed: document.getElementById('seed').value ? parseInt(document.getElementById('seed').value) : null,
  };
}

let previewTimer = null;
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(previewCount, 300);
}

async function previewCount() {
  const sel = collectSelection();
  if (!sel.chapter) { document.getElementById('count-preview').textContent = '-'; return; }
  const data = await fetchJSON('/api/preview_count', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(sel),
  });
  document.getElementById('count-preview').textContent = data.count;
}

async function generate() {
  const sel = collectSelection();
  if (!sel.chapter) { alert('대단원을 선택하세요'); return; }
  const body = Object.assign({}, sel, {
    title: document.getElementById('title').value || '문제집',
    forms: document.getElementById('forms').value.split(',').map(s => s.trim()).filter(Boolean),
    show_path: document.getElementById('showPath').checked,
    separate_answer_key: document.getElementById('separateAnswer').checked,
    with_explanation: document.getElementById('withExplanation').checked,
    shuffle_problem_order: document.getElementById('shuffleProblemOrder').checked,
    shuffle_choices: document.getElementById('shuffleChoices').checked,
    formats: Array.from(document.querySelectorAll('.fmt:checked')).map(cb => cb.value),
  });

  const btn = document.getElementById('genBtn');
  btn.disabled = true;
  btn.textContent = '생성 중... (HWP는 시간이 좀 걸립니다)';
  document.getElementById('result').innerHTML = '';
  try {
    const data = await fetchJSON('/api/generate', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    if (!data.ok) {
      document.getElementById('result').textContent = '오류: ' + data.error;
    } else {
      const links = data.files.map(f =>
        `<a class="dl" href="/api/download/${data.run_id}/${encodeURIComponent(f)}">${esc(f)}</a>`
      ).join('');
      document.getElementById('result').innerHTML = `<p>${data.count}문제로 생성 완료</p>` + links;
    }
  } catch (e) {
    document.getElementById('result').textContent = '오류: ' + e;
  } finally {
    btn.disabled = false;
    btn.textContent = '시험지 생성';
  }
}

loadChapters();
</script>
</body></html>
"""


UPLOAD_PAGE_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>자료 업로드</title>
<style>
body{font-family:sans-serif;max-width:700px;margin:30px auto;line-height:1.7}
label{display:block;margin:10px 0}
button{padding:8px 16px;font-size:14px;cursor:pointer}
#result{margin-top:16px}
#result div{padding:2px 0}
nav{margin-bottom:16px}
nav a{margin-right:12px}
</style></head>
<body>
<nav><a href="/">시험지 생성</a> &middot; <a href="/upload">자료 업로드</a></nav>
<h2>새 자료 업로드</h2>
<p style="color:#555">형식과 과목은 직접 골라주세요 - 파일 내용을 보고 자동으로 형식을 알아내지는 않습니다.
지금까지 다뤄본 적 없는 새로운 자료 형식은 이 화면으로 처리할 수 없고, 별도로 분석 작업이 필요합니다.</p>

<label>파이프라인 <select id="pipeline"></select></label>
<label>과목(대단원 이름) <input id="subject" size="20" placeholder="예: 공통수학1"></label>
<label>파일 <input id="file" type="file"></label>
<div id="extra"></div>
<button id="uploadBtn" onclick="doUpload()">업로드 및 추출</button>
<div id="result"></div>

<script>
function esc(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

let pipelines = {};
const EXTRA_LABELS = {
  unit_title_override: '단원명 강제 지정(선택 - 파일 내부에 적힌 단원명이 틀렸을 때만)',
  image_out_dir: '이미지 저장 폴더(비우면 problem_images/과목명)',
  section_names_csv: '대단원 이름들(콤마로 구분, PDF 안 대단원 순서와 똑같이)',
};

async function init() {
  const r = await fetch('/api/pipelines');
  pipelines = await r.json();
  const sel = document.getElementById('pipeline');
  sel.innerHTML = Object.keys(pipelines).map(k => `<option value="${esc(k)}">${esc(k)}</option>`).join('');
  sel.addEventListener('change', renderExtra);
  renderExtra();
}

function renderExtra() {
  const key = document.getElementById('pipeline').value;
  const p = pipelines[key];
  const box = document.getElementById('extra');
  if (!p) { box.innerHTML = ''; return; }
  box.innerHTML = p.extra_fields.map(f =>
    `<label>${esc(EXTRA_LABELS[f] || f)} <input id="extra_${esc(f)}" size="40"></label>`
  ).join('') + `<p style="color:#888">필요한 파일 형식: ${esc(p.file_ext)}</p>`;
}

async function doUpload() {
  const key = document.getElementById('pipeline').value;
  const p = pipelines[key];
  const fileInput = document.getElementById('file');
  if (!fileInput.files.length) { alert('파일을 선택하세요'); return; }

  const fd = new FormData();
  fd.append('pipeline', key);
  fd.append('subject', document.getElementById('subject').value);
  fd.append('file', fileInput.files[0]);
  (p.extra_fields || []).forEach(f => {
    fd.append(f, document.getElementById('extra_' + f).value);
  });

  const btn = document.getElementById('uploadBtn');
  btn.disabled = true;
  btn.textContent = '처리 중...';
  document.getElementById('result').innerHTML = '';
  try {
    const r = await fetch('/api/upload', {method: 'POST', body: fd});
    const data = await r.json();
    if (!data.ok) {
      document.getElementById('result').textContent = '오류: ' + data.error;
    } else {
      document.getElementById('result').innerHTML = '<p>완료</p>' +
        data.results.map(step => `<div>${esc(JSON.stringify(step))}</div>`).join('');
    }
  } catch (e) {
    document.getElementById('result').textContent = '오류: ' + e;
  } finally {
    btn.disabled = false;
    btn.textContent = '업로드 및 추출';
  }
}

init();
</script>
</body></html>
"""


if __name__ == "__main__":
    print("http://127.0.0.1:5058 에서 열어보세요")
    app.run(port=5058, debug=False)
