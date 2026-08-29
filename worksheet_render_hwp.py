"""선별된 문제 목록을 실제 .hwp 파일로 렌더링한다 (한글 COM 자동화).

- 이미지 문제(image_paths 있음): 이미지를 그대로 삽입.
- 텍스트/LaTeX 문제: $...$ 로 감싸인 부분만 latex_to_hwp_eq로 변환해 HWP
  자체 수식 객체로 삽입하고, 나머지는 일반 텍스트로 삽입한다.

주의(전부 실제 COM 자동화로 직접 검증한 내용, scratchpad 테스트 참고):
- InsertPicture와 SaveAs 둘 다 경로에 한글/공백이 섞이면 응답 없이 멈춘다
  (진짜 확인됨 - 이 프로젝트 작업 폴더 자체가 한글 경로라 실제로 걸리는
  문제). 그래서 이미지 삽입과 최종 저장 모두 ASCII 전용 임시 경로를 거친
  뒤, 완성된 파일을 일반 파일시스템 이동(shutil.move)으로 최종 목적지에
  옮긴다 - 파일 이동은 HWP COM을 안 거치므로 한글 경로여도 문제없다.
- SetMessageBoxMode(0x1FFFF)를 안 걸면 저장 확인 등 숨겨진 대화상자에서
  무한 대기할 수 있다.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

# 이 컴퓨터의 시스템 기본 임시 폴더(tempfile.gettempdir())가 다른 프로그램에
# 의해 C:\Users\Public\Documents\ESTsoft\CreatorTemp 로 재지정되어 있는데,
# 이 경로에서 HWP.SaveAs가 응답 없이 멈추는 걸 실제로 확인했다(원인 불명 -
# 아마 HWP의 파일 경로 보안 모듈이 이 폴더를 승인하지 않는 듯). 그래서
# ASCII 임시 경로가 필요한 곳(이미지 복사, 중간 저장)은 항상 사용자 프로필
# 아래의 실제 Temp 폴더를 직접 지정해서 쓴다.
_SAFE_TMP_BASE = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "AppData" / "Local" / "Temp"

from models import Problem
from latex_to_hwp_eq import latex_to_hwp_eq
from worksheet_select import describe_problem_path
from text_normalize import strip_watermark_noise
from condition_box import split_condition_block

_MATH_SPLIT_RE = re.compile(r'\$([^$]+)\$')
_CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧']


def _get_hwp():
    import win32com.client as win32
    hwp = win32.Dispatch("HWPFrame.HwpObject")
    hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModuleExample")
    hwp.SetMessageBoxMode(0x1FFFF)
    hwp.XHwpWindows.Item(0).Visible = False
    return hwp


def _insert_text(hwp, text: str) -> None:
    if not text:
        return
    # HWP의 InsertText.Text는 줄바꿈으로 '\n'이 아니라 '\r'을 요구한다 -
    # 직접 확인함: 'AAA\nBBB'를 넣으면 "AAABBB"로 그냥 이어 붙고, 'AAA\rBBB'를
    # 넣으면 실제로 두 줄로 나뉜다. 지금까지 이 프로젝트 전역에서 '\n'을
    # 써 왔는데(조건박스의 테이블 셀 안 문제와는 별개로, 본문에서도 항상
    # 이랬다) 실제로는 한 번도 제대로 줄바꿈이 된 적이 없었다는 뜻이라
    # 이 함수 하나만 고치면 전체가 같이 고쳐진다.
    act = hwp.HParameterSet.HInsertText
    hwp.HAction.GetDefault("InsertText", act.HSet)
    act.Text = text.replace("\r\n", "\n").replace("\n", "\r")
    hwp.HAction.Execute("InsertText", act.HSet)


def _insert_equation(hwp, latex: str) -> None:
    try:
        script = latex_to_hwp_eq(latex)
    except Exception:
        _insert_text(hwp, latex)
        return
    eq = hwp.HParameterSet.HEqEdit
    hwp.HAction.GetDefault("EquationCreate", eq.HSet)
    eq.string = script
    eq.EqFontName = "HYhwpEQ"
    eq.BaseUnit = 1000
    eq.Version = "Equation Version 60"
    eq.LineMode = 0
    hwp.HAction.Execute("EquationCreate", eq.HSet)


def _insert_mixed_text(hwp, text: str) -> None:
    """일반 텍스트 안에 $...$ 로 감싸인 LaTeX 조각이 섞여 있는 문자열을,
    텍스트/수식 조각으로 번갈아 삽입한다."""
    pos = 0
    for m in _MATH_SPLIT_RE.finditer(text):
        if m.start() > pos:
            _insert_text(hwp, text[pos:m.start()])
        _insert_equation(hwp, m.group(1))
        pos = m.end()
    if pos < len(text):
        _insert_text(hwp, text[pos:])


_MAX_IMG_WIDTH_MM = 140  # A4 기준 인쇄 가능 폭에 맞춘 최대 삽입 폭
_ASSUMED_DPI = 96  # HWP가 InsertPicture 시 픽셀 크기를 물리적 크기로 환산할 때 쓰는 기준(실측)
_MAX_IMG_WIDTH_PX = round(_MAX_IMG_WIDTH_MM / 25.4 * _ASSUMED_DPI)


def _insert_image(hwp, image_path: str, ascii_tmp_dir: Path) -> None:
    """InsertPicture의 Width/Height 인자는 실제로는 무시된다(직접 COM
    테스트로 확인 - sizeoption 0~3 전부 원본 픽셀 크기 그대로 삽입됨).
    그래서 삽입 전에 이미지 파일 자체를 픽셀 단위로 축소해서 넘긴다."""
    src = Path(image_path)
    if not src.is_file():
        return
    ascii_copy = ascii_tmp_dir / f"img_{abs(hash(str(src)))}{src.suffix}"
    if not ascii_copy.exists():
        try:
            from PIL import Image
            with Image.open(src) as im:
                if im.width > _MAX_IMG_WIDTH_PX:
                    ratio = _MAX_IMG_WIDTH_PX / im.width
                    im = im.resize((_MAX_IMG_WIDTH_PX, round(im.height * ratio)), Image.LANCZOS)
                im.save(ascii_copy)
        except Exception:
            shutil.copy(src, ascii_copy)

    hwp.InsertPicture(str(ascii_copy), True, 0, False, False, 0, 0, 0)


_CONDITION_BOX_WIDTH_MM = 156  # A4 기준 인쇄 가능 폭에 맞춘 박스 너비


def _insert_condition_box(hwp, items: list[str]) -> None:
    """"(가) ... (나) ..." 조건 나열을 테두리 박스(1x1 표)로 감싸 삽입한다.
    실제 COM으로 검증한 방식: 표를 만들고 셀 안에 텍스트/수식을 넣은 뒤
    TableColBegin+CloseEx로 표 밖으로 빠져나온다."""
    tc = hwp.HParameterSet.HTableCreation
    hwp.HAction.GetDefault("TableCreate", tc.HSet)
    tc.Rows = 1
    tc.Cols = 1
    tc.WidthType = 0
    tc.WidthValue = hwp.MiliToHwpUnit(_CONDITION_BOX_WIDTH_MM)
    tc.HeightType = 1
    tc.HeightValue = hwp.MiliToHwpUnit(15)
    hwp.HAction.Execute("TableCreate", tc.HSet)

    for i, item in enumerate(items):
        if i > 0:
            hwp.Run("BreakPara")
        _insert_mixed_text(hwp, item)

    hwp.Run("TableColBegin")
    hwp.Run("CloseEx")


def _insert_problem(
    hwp, index: int, p: Problem, ascii_tmp_dir: Path, show_path: bool,
    choice_order: list[int] | None = None,
) -> None:
    _insert_text(hwp, f"{index}. ")
    if show_path:
        _insert_text(hwp, f"[{describe_problem_path(p)}]\n")

    if p.image_paths:
        for path in json.loads(p.image_paths):
            _insert_image(hwp, path, ascii_tmp_dir)
        _insert_text(hwp, "\n")
    elif p.stem_latex:
        stem = strip_watermark_noise(p.stem_latex)
        main_text, condition_items, trailing_text = split_condition_block(stem)
        _insert_mixed_text(hwp, main_text)
        _insert_text(hwp, "\n")
        if condition_items:
            _insert_condition_box(hwp, condition_items)
            _insert_text(hwp, "\n")
            if trailing_text:
                _insert_mixed_text(hwp, trailing_text)
                _insert_text(hwp, "\n")
        if p.choices_latex:
            try:
                choices = json.loads(p.choices_latex)
            except (json.JSONDecodeError, TypeError):
                choices = None
            if choices:
                order = choice_order if choice_order is not None else list(range(len(choices)))
                for i, orig_i in enumerate(order):
                    mark = _CIRCLED[i] if i < len(_CIRCLED) else str(i + 1)
                    _insert_text(hwp, f"{mark} ")
                    _insert_mixed_text(hwp, strip_watermark_noise(choices[orig_i]))
                    _insert_text(hwp, "   ")
                _insert_text(hwp, "\n")
    _insert_text(hwp, "\n")


def _finalize_save(hwp, ascii_tmp_dir: Path, tmp_save_path: Path, out_path: str) -> None:
    final_path = Path(out_path).resolve()
    final_path.parent.mkdir(parents=True, exist_ok=True)
    # hwp.Quit() 직후에도 잠깐 파일 핸들이 안 풀릴 때가 있어(HWP 프로세스가
    # 완전히 종료되기 전) 짧게 재시도한다.
    last_err = None
    for _ in range(20):
        try:
            shutil.move(str(tmp_save_path), str(final_path))
            last_err = None
            break
        except PermissionError as e:
            last_err = e
            time.sleep(0.5)
    if last_err is not None:
        raise last_err
    shutil.rmtree(ascii_tmp_dir, ignore_errors=True)


def _insert_explanation_section(hwp, problems: list[Problem]) -> None:
    """해설이 있는 문제만 번호와 함께 나열한다 (없는 문제는 조용히 건너뜀)."""
    if not any(p.explanation for p in problems):
        return
    _insert_text(hwp, "\n해설\n")
    for i, p in enumerate(problems, start=1):
        if not p.explanation:
            continue
        _insert_text(hwp, f"{i}. ")
        _insert_mixed_text(hwp, strip_watermark_noise(p.explanation))
        _insert_text(hwp, "\n")


def save_worksheet_hwp(
    problems: list[Problem],
    title: str,
    out_path: str,
    show_path: bool = False,
    choice_orders: list[list[int] | None] | None = None,
    display_answers: list[str | None] | None = None,
    include_answer_key: bool = True,
    include_explanations: bool = False,
) -> None:
    """choice_orders/display_answers를 주면 A형/B형처럼 보기 순서가 섞인
    버전을 그대로 반영한다. include_answer_key=False면 정답 부분을 생략한다
    (별도 정답지가 필요할 때 save_answer_key_hwp와 함께 쓴다)."""
    hwp = _get_hwp()
    _SAFE_TMP_BASE.mkdir(parents=True, exist_ok=True)
    ascii_tmp_dir = Path(tempfile.mkdtemp(prefix="worksheet_imgs_", dir=str(_SAFE_TMP_BASE)))
    try:
        hwp.Run("FileNew")
        hwp.Run("MoveDocBegin")

        act = hwp.HParameterSet.HInsertText
        hwp.HAction.GetDefault("InsertText", act.HSet)
        act.Text = f"{title}\n\n"
        hwp.HAction.Execute("InsertText", act.HSet)

        for i, p in enumerate(problems, start=1):
            order = choice_orders[i - 1] if choice_orders else None
            _insert_problem(hwp, i, p, ascii_tmp_dir, show_path, order)

        if include_answer_key:
            answers = display_answers if display_answers is not None else [p.answer for p in problems]
            _insert_text(hwp, "\n정답\n")
            answer_line = "   ".join(f"{i}. {a or '-'}" for i, a in enumerate(answers, start=1))
            _insert_text(hwp, answer_line + "\n")
            if include_explanations:
                _insert_explanation_section(hwp, problems)

        tmp_save_path = ascii_tmp_dir / "out.hwp"
        hwp.SaveAs(str(tmp_save_path), "HWP")
    finally:
        hwp.Quit()

    _finalize_save(hwp, ascii_tmp_dir, tmp_save_path, out_path)


def save_answer_key_hwp(
    title: str,
    problems: list[Problem],
    out_path: str,
    display_answers: list[str | None] | None = None,
    include_explanations: bool = False,
) -> None:
    """정답만 담은 별도 .hwp(정답지)를 생성한다."""
    answers = display_answers if display_answers is not None else [p.answer for p in problems]
    hwp = _get_hwp()
    _SAFE_TMP_BASE.mkdir(parents=True, exist_ok=True)
    ascii_tmp_dir = Path(tempfile.mkdtemp(prefix="worksheet_answers_", dir=str(_SAFE_TMP_BASE)))
    try:
        hwp.Run("FileNew")
        hwp.Run("MoveDocBegin")
        _insert_text(hwp, f"{title} - 정답\n\n")
        answer_line = "   ".join(f"{i}. {a or '-'}" for i, a in enumerate(answers, start=1))
        _insert_text(hwp, answer_line + "\n")
        if include_explanations:
            _insert_explanation_section(hwp, problems)
        tmp_save_path = ascii_tmp_dir / "out.hwp"
        hwp.SaveAs(str(tmp_save_path), "HWP")
    finally:
        hwp.Quit()

    _finalize_save(hwp, ascii_tmp_dir, tmp_save_path, out_path)
