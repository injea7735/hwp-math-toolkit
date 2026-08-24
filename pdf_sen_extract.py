"""
쎈수학 미적분Ⅱ "문제.pdf"(스캔/래스터 - 텍스트 레이어 없음)에서 문제를
유형별로 잘라낸다.

문제 번호가 이미지로만 존재해서(get_text가 빈 문자열) 색상+연결요소로
번호 위치를 찾고, 그 작은 크롭만 Tesseract OCR로 읽는다. 페이지에는
세 종류의 색깔 있는 마커가 나온다:

  - 초록 알약 "유형 NN"       -> 유형 경계. 오른쪽 절반에 2자리 번호가 있다.
  - 빨강 알약 "NNNN | 대표 문제" -> 그 유형의 대표문제 시작 위치.
  - 초록 굵은 4자리 번호(낱개 획 4개가 붙어 있음) -> 일반 문제 시작 위치.
    ("개념 확인" 절의 문제 번호는 주황색이지만 크기·모양은 같아서 같은
    로직으로 잡힌다 - 유형 알약을 아직 못 만난 상태면 그냥 버린다.)

유형 이름·대표문제 번호·정답은 hwp_sen_daepyo_parse로 이미 뽑아 둔 HWP
자료가 더 정확하므로(정답 원문자 OCR은 불안정) 그쪽을 신뢰하고, PDF에서는
"몇 번째 유형 알약을 만났는지"라는 순서만 대응시킨다. 유형 알약 OCR
결과 앞에 잡음 숫자가 하나 더 붙는 경향이 있어(글자 "형"의 획을 숫자로
오인) 뒤 2자리만 쓰고, 그마저 안 맞으면 내부 순번 카운터를 믿는다.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import fitz
import numpy as np
import pytesseract
from PIL import Image
from scipy import ndimage

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ.setdefault('TESSDATA_PREFIX', r'C:\Users\Ace\tessdata')

DPI = 150

# 과목마다 파일명 순서 = 책 순서(다른 출처로 이미 검증됨). 해당 과목의
# import_sen_daepyo_types_*.py가 쓰는 FILE_TO_SUBSECTION과 같은 매핑을
# 파일 열거 순서로 그대로 쓴다. extract_problems()에 인자로 넘긴다.
MI2_SUBSECTION_ORDER = [
    ('수열의 극한', '수열의 극한'),
    ('수열의 극한', '급수'),
    ('미분법', '지수함수와 로그함수의 미분'),
    ('미분법', '삼각함수의 미분'),
    ('미분법', '여러 가지 미분법'),
    ('미분법', '도함수의 활용 ⑴'),
    ('미분법', '도함수의 활용 ⑵'),
    ('적분법', '여러 가지 적분법'),
    ('적분법', '정적분'),
    ('적분법', '정적분의 활용'),
]

ALGEBRA_SUBSECTION_ORDER = [
    ('지수함수와 로그함수', '지수'),
    ('지수함수와 로그함수', '로그'),
    ('지수함수와 로그함수', '지수함수'),
    ('지수함수와 로그함수', '로그함수'),
    ('삼각함수', '삼각함수'),
    ('삼각함수', '삼각함수의 그래프'),
    ('삼각함수', '삼각함수의 활용'),
    ('수열', '등차수열과 등비수열'),
    ('수열', '수열의 합'),
    ('수열', '수학적 귀납법'),
]

PROBSTAT_SUBSECTION_ORDER = [
    ('경우의 수', '여러 가지 순열'),
    ('경우의 수', '중복조합과 이항정리'),
    ('확률', '확률의 뜻과 활용'),
    ('확률', '조건부확률'),
    ('통계', '확률변수와 확률분포'),
    ('통계', '이항분포와 정규분포'),
    ('통계', '통계적 추정'),
]


@dataclass
class SenProblem:
    section_name: str
    subsection_name: str
    type_no: str
    type_title: str
    number: str | None       # OCR로 읽은 4자리 번호 (실패하면 None)
    is_daepyo: bool
    answer: str | None       # 대표문제면 HWP 정답, 아니면 None
    page_index: int
    image_path: str


def _page_array(page):
    pix = page.get_pixmap(dpi=DPI)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)


def _boxes_from_mask(arr, mask, sat):
    labels, n = ndimage.label(mask, structure=np.ones((3, 3)))
    boxes = []
    for label_id, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        w, h = x1 - x0, y1 - y0
        if h < 8 or w < 3:
            continue
        # 가운데 픽셀 하나만 보면 안티에일리어싱/흰 배경과 섞인 픽셀을 우연히
        # 골라 색이 옅게 나올 수 있다(예: 진짜 초록(78,167,123)이 흰 배경과
        # 섞여 (152,205,202)처럼 잡힘) - 그 부품 안에서 채도가 가장 높은
        # 픽셀(원색에 가장 가까운 지점)을 대표색으로 쓴다.
        comp_mask = labels[y0:y1, x0:x1] == label_id
        sub_sat = sat[y0:y1, x0:x1]
        py, px = np.unravel_index(np.argmax(np.where(comp_mask, sub_sat, -1)), sub_sat.shape)
        color = tuple(int(v) for v in arr[y0 + py, x0 + px])
        boxes.append((x0, y0, w, h, color))
    return boxes


def _find_colored_boxes(arr):
    """숫자 조각 등 색 종류를 안 가리고 찾을 때 쓰는 범용 버전."""
    r = arr[:, :, 0].astype(int); g = arr[:, :, 1].astype(int); b = arr[:, :, 2].astype(int)
    mx = np.maximum(np.maximum(r, g), b); mn = np.minimum(np.minimum(r, g), b)
    sat = mx - mn
    colorful = (sat > 40) & (mx > 90)
    return _boxes_from_mask(arr, colorful, sat)


def _find_green_boxes(arr):
    """유형 알약 전용. 초록 우세 픽셀만 라벨링해서, 옆에 붙은 금색 "개념" 표찰
    같은 다른 색과 한 부품으로 뭉쳐 대표색이 오염되는 걸 애초에 막는다."""
    r = arr[:, :, 0].astype(int); g = arr[:, :, 1].astype(int); b = arr[:, :, 2].astype(int)
    mx = np.maximum(np.maximum(r, g), b); mn = np.minimum(np.minimum(r, g), b)
    sat = mx - mn
    greenish = (sat > 40) & (mx > 90) & (g > r) & (g >= b)
    return _boxes_from_mask(arr, greenish, sat)


def _find_red_boxes(arr):
    """대표문제 알약 전용. 빨강/주황 우세 픽셀만 라벨링한다."""
    r = arr[:, :, 0].astype(int); g = arr[:, :, 1].astype(int); b = arr[:, :, 2].astype(int)
    mx = np.maximum(np.maximum(r, g), b); mn = np.minimum(np.minimum(r, g), b)
    sat = mx - mn
    reddish = (sat > 40) & (mx > 90) & (r > g) & (r > b)
    return _boxes_from_mask(arr, reddish, sat)


def _is_type_pill(box):
    x, y, w, h, (r, g, b) = box
    return 50 <= w <= 80 and 26 <= h <= 42 and g > r + 25 and g > b + 12


def _is_daepyo_pill(box):
    x, y, w, h, (r, g, b) = box
    return 110 <= w <= 160 and 22 <= h <= 36 and r > g + 80 and r > b + 100


def _is_concept_heading(box):
    """소단원 안의 "04-4 독립시행의 확률" 같은 개념 소제목 알약(진한 주황).
    문제/유형/대표문제와 무관하지만, 문제 이미지를 자를 때 그 다음 문제로
    넘어가지 않고 이 알약까지 통째로 잘려 들어가지 않도록 경계로만 쓴다."""
    x, y, w, h, (r, g, b) = box
    return 50 <= w <= 80 and 26 <= h <= 42 and r > g and g - b > 80


def _is_digit_fragment(box):
    x, y, w, h, (r, g, b) = box
    return 6 <= w <= 15 and 14 <= h <= 24


def _cluster_digits(fragments):
    """가까이 붙은 낱개 획들을 같은 줄에서 x순서로 묶어 4자리 그룹으로 만든다."""
    frags = sorted(fragments, key=lambda b: (b[1], b[0]))
    used = [False] * len(frags)
    groups = []
    for i, f in enumerate(frags):
        if used[i]:
            continue
        x0, y0, w0, h0, _ = f
        group = [f]
        used[i] = True
        cy = y0 + h0 / 2
        last_x1 = x0 + w0
        for j in range(i + 1, len(frags)):
            if used[j]:
                continue
            x1, y1, w1, h1, _ = frags[j]
            if abs((y1 + h1 / 2) - cy) < 6 and 0 <= x1 - last_x1 <= 8:
                group.append(frags[j])
                used[j] = True
                last_x1 = x1 + w1
        if len(group) == 4:
            gx0 = min(g[0] for g in group)
            gy0 = min(g[1] for g in group)
            gx1 = max(g[0] + g[2] for g in group)
            gy1 = max(g[1] + g[3] for g in group)
            groups.append((gx0, gy0, gx1 - gx0, gy1 - gy0))
    return groups


def _resync_current_type(entries, current_type, daepyo_digits):
    """대표문제 알약의 4자리 OCR로 유형 순번 드리프트를 자기 교정한다.

    유형 알약 자체의 순번(2자리) OCR은 잡음이 많아서, 페이지 렌더링
    문제로 진짜 유형 알약 하나를 통째로 못 찾으면(예: 색상 오검출) 내부
    순번 카운터가 그 뒤로 계속 한 칸씩 밀린다 - 그 상태로도 각 유형의
    문제 번호가 그럴듯하게 증가하기 때문에 조용히 넘어가기 쉽다. 반면
    대표문제 번호(4자리) OCR은 훨씬 안정적으로 읽힌다. 지금 카운터가
    가리키는 유형과 실제 OCR 번호가 다르면서, 그 번호가 같은 소단원의
    "다른" 유형과 정확히 일치하면 그쪽이 진짜라고 보고 되돌려준다.
    일치하는 게 없거나(OCR 실패 등) 이미 같으면 None(교정 없음).
    """
    if len(daepyo_digits) != 4 or daepyo_digits == current_type.problem_no:
        return None
    match = next((e for e in entries if e.problem_no == daepyo_digits), None)
    if match is not None and match is not current_type:
        return match
    return None


def _save_trimmed(pix, img_path, bottom_pad=25, min_height=60):
    """문제 하나의 크롭 아래쪽 빈 여백을 잘라내고 저장한다.

    크롭 경계는 "다음 마커가 나오기 전까지"로 정하다 보니, 다음 마커가
    한참 아래(페이지 끝이나 유형 사이 간격)에 있으면 실제 문제 내용은
    위쪽에 다 몰려 있고 아래는 빈 백지로 남는다 - 이미지 미리보기에서
    문제가 위로 쏠려 보이고, 나중에 다른 내용이 안 보일까 걱정하게 만든다.
    실제 내용(흰색이 아닌 픽셀)이 있는 마지막 줄까지만 남긴다.
    """
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    non_white = np.any(arr[:, :, :3] < 250, axis=2)
    rows_with_content = np.where(non_white.any(axis=1))[0]
    if len(rows_with_content) == 0:
        pix.save(img_path)
        return
    first_row = int(rows_with_content[0])
    last_row = int(rows_with_content[-1]) + bottom_pad
    last_row = max(last_row, first_row + min_height)  # 최소 높이는 보장
    last_row = min(last_row, pix.height)
    if last_row >= pix.height:
        pix.save(img_path)
        return
    mode = 'RGBA' if pix.n == 4 else 'RGB'
    img = Image.frombuffer(mode, (pix.width, pix.height), pix.samples, 'raw', mode, 0, 1)
    img.crop((0, 0, pix.width, last_row)).save(img_path)


def _ocr_digits(page, box, pad=4, max_w=None, align='left'):
    x, y, w, h = box[:4]
    if max_w is not None and max_w < w:
        if align == 'right':
            x = x + w - max_w
        w = max_w
    rect = fitz.Rect((x - pad) * 72 / DPI, (y - pad) * 72 / DPI, (x + w + pad) * 72 / DPI, (y + h + pad) * 72 / DPI)
    pix = page.get_pixmap(dpi=600, clip=rect)
    img = Image.open(__import__('io').BytesIO(pix.tobytes('png'))).convert('L')
    img = img.resize((img.width * 2, img.height * 2))
    img = img.point(lambda v: 0 if v < 180 else 255)
    text = pytesseract.image_to_string(img, config='--psm 7 -c tessedit_char_whitelist=0123456789')
    return text.strip()


def _page_markers(page):
    """페이지 하나에서 (kind, bbox, column) 마커 목록을 (column, y) 순서로 낸다."""
    arr = _page_array(page)
    W = arr.shape[1]

    markers = []
    # 유형 알약(초록)과 대표문제 알약(빨강)은 색상 마스크 단계부터 따로
    # 라벨링한다 - 옆에 붙은 "개념 07-9" 같은 금색 표찰과 한 부품으로
    # 뭉쳐서 대표색이 오염되는 걸(예: (224,222,134) 같은 애매한 색) 막는다.
    for b in _find_green_boxes(arr):
        if _is_type_pill(b):
            x = b[0]
            column = 0 if x < W / 2 else 1
            markers.append(('type_pill', b, column))
    for b in _find_red_boxes(arr):
        x = b[0]
        column = 0 if x < W / 2 else 1
        if _is_daepyo_pill(b):
            markers.append(('daepyo_pill', b, column))
        elif _is_concept_heading(b):
            markers.append(('heading', b, column))

    boxes = _find_colored_boxes(arr)
    digit_frags = [b for b in boxes if _is_digit_fragment(b)]
    for gx0, gy0, gw, gh in _cluster_digits(digit_frags):
        column = 0 if gx0 < W / 2 else 1
        markers.append(('number', (gx0, gy0, gw, gh, None), column))

    markers.sort(key=lambda m: (m[2], m[1][1]))
    return markers


def extract_problems(
    pdf_path: str, hwp_dir: str, out_dir: str,
    subsection_order: list[tuple[str, str]],
    page_range: range | None = None,
) -> tuple[list[SenProblem], list[str]]:
    from hwp_sen_daepyo_parse import extract_representative_types

    hwp_files = sorted(f for f in os.listdir(hwp_dir) if f.endswith('.hwp'))
    if len(hwp_files) != len(subsection_order):
        raise ValueError(f'HWP 파일 수({len(hwp_files)})가 예상({len(subsection_order)})과 다름')
    subsection_entries = [
        extract_representative_types(os.path.join(hwp_dir, fn)) for fn in hwp_files
    ]

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)

    results: list[SenProblem] = []
    warnings: list[str] = []
    sub_idx = 0
    next_type_no = 1          # 이번 소단원에서 다음에 나올 유형 순번(기대값)
    current_type = None       # subsection_entries[sub_idx][next_type_no - 2] (마지막으로 확정한 유형)
    type_upper_bound = None   # 이번 유형 소속 문제번호의 배타적 상한(다음 유형의 대표문제 번호)
    stem = Path(pdf_path).stem

    for pno in (page_range if page_range is not None else range(doc.page_count)):
        page = doc[pno]
        markers = _page_markers(page)
        if not markers:
            continue

        W, H = page.rect.width, page.rect.height
        col_bounds = [(0, W / 2), (W / 2, W)]

        by_col: dict[int, list] = {0: [], 1: []}
        for kind, box, column in markers:
            by_col[column].append((kind, box))

        for column, col_markers in by_col.items():
            col_markers.sort(key=lambda m: m[1][1])
            # 진짜 유형 알약은 그 뒤(다음 유형 알약이 나오기 전) 어딘가에
            # 그 유형의 대표문제 빨강 알약이 붙어 나온다 - 바로 다음 마커일
            # 필요는 없다(예: 이전 유형이 연습문제 없이 바로 다음 유형으로
            # 이어지면 유형 알약 두 개가 연달아 나올 수 있다). 이 짝을 못
            # 찾는 type_pill은 색상 오검출(예: 표지의 장식 요소)이므로 거른다.
            def _has_daepyo_before_next_type(idx):
                for j in range(idx + 1, len(col_markers)):
                    if col_markers[j][0] == 'type_pill':
                        return False
                    if col_markers[j][0] == 'daepyo_pill':
                        return True
                return False

            col_markers = [
                m for i, m in enumerate(col_markers)
                if m[0] != 'type_pill' or _has_daepyo_before_next_type(i)
            ]
            for i, (kind, box) in enumerate(col_markers):
                y0 = box[1]
                y1 = col_markers[i + 1][1][1] if i + 1 < len(col_markers) else H * DPI / 72

                if kind == 'heading':
                    continue  # 개념 소제목 알약 - 내용은 안 쓰고 자르는 경계로만 쓴다

                if kind == 'type_pill':
                    ocr = _ocr_digits(page, box, max_w=38, align='right')
                    digits = re.sub(r'\D', '', ocr)[-2:]
                    entries = subsection_entries[sub_idx]
                    type_no = next_type_no  # 내부 순번을 우선 신뢰(OCR은 잡음이 있음)
                    if not (digits.isdigit() and int(digits) == next_type_no):
                        warnings.append(
                            f'p{pno} col{column} 유형 알약 순번 확인 실패: 기대={next_type_no} OCR={ocr!r}'
                        )
                    if type_no > len(entries):
                        # 이번 소단원의 유형이 이미 다 나왔는데 또 유형 알약이 나옴
                        # -> 다음 소단원으로 넘어간 것. 새 소단원의 1번 유형으로 재해석.
                        if sub_idx + 1 < len(subsection_entries):
                            sub_idx += 1
                            entries = subsection_entries[sub_idx]
                            type_no = 1
                        else:
                            current_type = None
                            continue
                    current_type = entries[type_no - 1]
                    next_type_no = type_no + 1
                    # 다음 유형의 대표문제 번호 = 이번 유형 번호의 배타적 상한.
                    # 마지막 유형이면 상한을 안 두고(다음 소단원 알약이 나올 때까지) 그냥 통과시킨다.
                    type_upper_bound = (
                        int(entries[type_no].problem_no) if type_no < len(entries) else None
                    )
                    continue

                if current_type is None:
                    continue  # 아직 유형 알약을 못 만남(개념 확인 절 등) - 대상 밖

                if y1 <= y0:
                    continue  # 겹친 마커 등으로 생긴 퇴화 영역 - 건너뜀

                x0, x1 = col_bounds[column]
                x0_pt, x1_pt = x0, x1
                y0_pt = y0 * 72 / DPI
                y1_pt = y1 * 72 / DPI
                clip = fitz.Rect(x0_pt, y0_pt, x1_pt, y1_pt)

                is_daepyo = kind == 'daepyo_pill'
                if is_daepyo:
                    ocr = _ocr_digits(page, box, max_w=58, align='left')
                    digits = re.sub(r'\D', '', ocr)
                    resynced = _resync_current_type(entries, current_type, digits)
                    if resynced is not None:
                        current_type = resynced
                        type_no = int(resynced.type_no)
                        next_type_no = type_no + 1
                        type_upper_bound = (
                            int(entries[type_no].problem_no) if type_no < len(entries) else None
                        )
                    number = current_type.problem_no
                    answer = current_type.answer
                    if digits and digits != number:
                        warnings.append(
                            f'p{pno} col{column} 유형{current_type.type_no}({current_type.title}): '
                            f'대표문제 예상={number} OCR={digits!r}'
                        )
                else:
                    ocr = _ocr_digits(page, box)
                    digits = re.sub(r'\D', '', ocr)
                    number = digits if len(digits) == 4 else None
                    answer = None
                    # 숫자 오독(예: 1<->7) 방지: 이번 유형 구간을 벗어나면 버린다
                    # - 틀린 번호를 저장하느니 번호 없이 이미지만 남기는 쪽이 낫다.
                    if number is not None:
                        lo = int(current_type.problem_no)
                        if int(number) < lo or (type_upper_bound is not None and int(number) >= type_upper_bound):
                            warnings.append(
                                f'p{pno} col{column} 유형{current_type.type_no}({current_type.title}): '
                                f'번호 {number} 가 유효 범위[{lo}, {type_upper_bound}) 밖 - 버림'
                            )
                            number = None

                section_name, subsection_name = subsection_order[sub_idx]
                img_name = f'{stem}_{pno:04d}_{number or f"col{column}-{i}"}.png'
                img_path = str(Path(out_dir) / img_name)
                try:
                    pix = page.get_pixmap(clip=clip, dpi=200)
                    _save_trimmed(pix, img_path)
                except Exception as exc:
                    warnings.append(f'p{pno} col{column} 이미지 저장 실패({clip}): {exc}')
                    continue

                results.append(SenProblem(
                    section_name=section_name, subsection_name=subsection_name,
                    type_no=str(current_type.type_no), type_title=current_type.title,
                    number=number, is_daepyo=is_daepyo, answer=answer,
                    page_index=pno, image_path=img_path,
                ))

    doc.close()
    return results, warnings


SUBJECT_SUBSECTION_ORDERS = {
    '대수': ALGEBRA_SUBSECTION_ORDER,
    '미적분2': MI2_SUBSECTION_ORDER,
    '확률과 통계': PROBSTAT_SUBSECTION_ORDER,
}

if __name__ == '__main__':
    import sys
    from collections import Counter

    subject = sys.argv[1]
    pdf_path = sys.argv[2]
    hwp_dir = sys.argv[3]
    out_dir = sys.argv[4]

    problems, warnings = extract_problems(pdf_path, hwp_dir, out_dir, SUBJECT_SUBSECTION_ORDERS[subject])
    with open('sen_extract_log.txt', 'w', encoding='utf-8') as f:
        f.write(f'총 문제 수: {len(problems)}\n')
        f.write(f'대표문제 수: {sum(1 for p in problems if p.is_daepyo)}\n')
        by_sub = Counter(p.subsection_name for p in problems)
        f.write(f'소단원별: {dict(by_sub)}\n')
        f.write(f'경고 {len(warnings)}건:\n')
        for w in warnings:
            f.write(f'  {w}\n')
    print('done, see sen_extract_log.txt')
