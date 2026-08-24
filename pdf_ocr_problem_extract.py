"""
쎈수학 미적분Ⅱ처럼 텍스트 레이어가 아예 없는(스캔) PDF에서 문제를 추출한다.

pdf_problem_extract.py(폰트/텍스트 메타데이터 기반)와 같은 목표지만, 이
PDF는 페이지 자체가 통째로 이미지라 OCR(Tesseract)을 거쳐야 한다.
확인된 것들:
  - 문제 번호(4자리, "0051" 등)는 검은 글씨/흰 배경이라 OCR이 잘 된다.
  - "유형 03" 같은 유형 배지는 초록 알약 모양 안에 흰 글씨로 그려져 있는데,
    이 장식체 폰트 자체를 Tesseract가 못 읽는다(마스킹/고해상도/여러 PSM
    다 시도해봤지만 실패) - 그래서 배지의 "존재"만 색상으로 감지해서 유형
    경계로 쓰고, 유형은 소단원 안에서 순번(유형 1, 유형 2 ...)으로 매긴다.
  - 배지 바로 옆에 나오는 유형 제목은 수식과 한글이 섞인 일반 텍스트라
    수식 부분은 깨지지만 끝의 한글 키워드(예: "...의 이용")는 대체로
    읽힌다 - 참고용 힌트로만 같이 저장한다.
  - 페이지 하단 각주에 "05 여러 가지 미분법"처럼 소단원 번호+이름이 찍혀
    있어 이걸로 소단원을 추적한다. 대단원은 이 각주에 나오는 대단원 한글
    이름(수열의 극한/미분법/적분법)으로 판별한다.

** 미완성 - 2026-08-22 세션 종료 시점 상태 **
아직 실사용 품질이 아니다. pages 15-24로 시범 실행한 결과:
  - 문제 번호 검출에 오탐이 많다 - 빽빽한 수식을 4자리 숫자로 잘못 읽는
    경우가 있어(예: 페이지 한 장에 진짜론 5~6개여야 할 문제가 16개로
    잡힘, 순서상 뜬금없는 번호("...038,089,040..."도 섞여 나옴). 폰트
    메타데이터가 있던 pdf_problem_extract.py와 달리 순수 OCR 텍스트에는
    "진짜 배지"와 "수식 오독"을 구분할 신뢰할 만한 신호가 없다 - 글자
    크기/위치 기반 필터링을 추가해야 할 걸로 보임(아직 안 함).
  - 소단원 각주 정규식이 시범 구간에서 한 번도 안 걸렸다(sub=None만 나옴)
    - 정규식 자체나 각주 인식 위치를 다시 봐야 함.
  - 유형 순번(type_seq)은 초록 배지 개수만 세는 방식이라 위 문제번호
    오탐과 결합하면 같이 틀어질 수 있음.
  - type_hint(배지 옆 한글 키워드)는 아직 코드에 연결 안 함(값이 항상 None).
다음 세션에서 이어감: 사용자가 미적분2 관련 자료를 더 보내주기로 함.
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

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ.setdefault('TESSDATA_PREFIX', r'C:\Users\Ace\tessdata')

DPI = 300
PROBLEM_NUMBER_RE = re.compile(r'^\d{4}$')
SUBSECTION_FOOTER_RE = re.compile(r'(\d{2})\s+([가-힣][가-힣 ]{2,20}[가-힣])\s*\d*\s*$')

# 초록 유형 배지 색(대략 RGB 60,150,110 부근) 검출용 범위
_BADGE_GREEN_LOW = (30, 120, 80)
_BADGE_GREEN_HIGH = (110, 190, 160)


@dataclass
class OcrProblem:
    number: str
    section_name: str | None
    subsection_name: str | None
    type_seq: int  # 소단원 안에서 몇 번째 유형인지(1부터)
    type_hint: str | None  # 유형 배지 옆 한글 키워드(있으면), 없으면 None
    page_index: int
    image_path: str
    text: str


def _ocr_page(img: Image.Image):
    return pytesseract.image_to_data(img, lang='kor+eng', output_type=pytesseract.Output.DICT)


def _footer_text(page, dpi: int) -> str:
    rect = page.rect
    clip = fitz.Rect(0, rect.height * 0.92, rect.width, rect.height)
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img, lang='kor+eng', config='--psm 7')


def _detect_green_blobs(img_arr: np.ndarray, page_width_px: int):
    """유형 배지(초록 알약)의 대략적인 (y, column) 위치 목록을 낸다.
    텍스트는 못 읽지만 색 블록의 존재/위치는 안정적으로 잡힌다."""
    r, g, b = img_arr[:, :, 0].astype(int), img_arr[:, :, 1].astype(int), img_arr[:, :, 2].astype(int)
    mask = (
        (r >= _BADGE_GREEN_LOW[0]) & (r <= _BADGE_GREEN_HIGH[0]) &
        (g >= _BADGE_GREEN_LOW[1]) & (g <= _BADGE_GREEN_HIGH[1]) &
        (b >= _BADGE_GREEN_LOW[2]) & (b <= _BADGE_GREEN_HIGH[2])
    )
    rows_with_green = np.where(mask.any(axis=1))[0]
    if len(rows_with_green) == 0:
        return []
    # 연속된 행 구간을 하나의 배지로 묶는다
    blobs = []
    start = rows_with_green[0]
    prev = rows_with_green[0]
    for y in rows_with_green[1:]:
        if y - prev > 5:
            blobs.append((start, prev))
            start = y
        prev = y
    blobs.append((start, prev))

    results = []
    for y0, y1 in blobs:
        if y1 - y0 < 5:  # 너무 얇으면(선/노이즈) 제외
            continue
        row_mask = mask[y0:y1 + 1]
        xs = np.where(row_mask.any(axis=0))[0]
        if len(xs) == 0:
            continue
        column = 0 if xs.min() < page_width_px / 2 else 1
        results.append({'y0': int(y0), 'y1': int(y1), 'x0': int(xs.min()), 'x1': int(xs.max()), 'column': column})
    return results


def _find_number_words(data: dict, page_width_px: int):
    markers = []
    n = len(data['text'])
    for i in range(n):
        text = data['text'][i].strip()
        if not PROBLEM_NUMBER_RE.match(text):
            continue
        x0, y0 = data['left'][i], data['top'][i]
        w, h = data['width'][i], data['height'][i]
        column = 0 if x0 < page_width_px / 2 else 1
        markers.append({'number': text, 'x0': x0, 'y0': y0, 'x1': x0 + w, 'y1': y0 + h, 'column': column})
    markers.sort(key=lambda m: (m['column'], m['y0']))
    return markers


def extract_problems(
    pdf_path: str, out_dir: str, section_names: list[str],
    page_range: range | None = None,
) -> list[OcrProblem]:
    doc = fitz.open(pdf_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    results: list[OcrProblem] = []
    current_section: str | None = None
    current_subsection: str | None = None
    type_seq = 0
    seen_subsection_key = None

    for pno in (page_range if page_range is not None else range(doc.page_count)):
        page = doc[pno]
        footer = _footer_text(page, DPI)

        for name in section_names:
            if name and name[:2] in footer:  # 대단원명 앞 2글자만 매칭(각주 폰트가 작아 일부만 읽힐 수 있음)
                current_section = name
                break

        m = SUBSECTION_FOOTER_RE.search(footer)
        if m:
            key = m.group(1)
            if key != seen_subsection_key:
                seen_subsection_key = key
                current_subsection = m.group(2).strip()
                type_seq = 0

        pix = page.get_pixmap(dpi=DPI)
        img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        img_arr = np.array(img)

        blobs = _detect_green_blobs(img_arr, pix.width)
        data = _ocr_page(img)
        markers = _find_number_words(data, pix.width)
        if not markers:
            continue

        # 이 페이지에 나온 배지 개수만큼 유형 순번을 올린다(배지 y좌표 순서대로)
        blobs.sort(key=lambda b: (b['column'], b['y0']))
        blob_ys = [b['y0'] for b in blobs]

        for mk in markers:
            # 이 문제 위치 이전에 새 배지가 몇 개 지났는지로 유형 순번 갱신
            if blobs:
                type_seq = max(type_seq, len([b for b in blobs if b['y0'] <= mk['y0']]))

            same_col = [m2 for m2 in markers if m2['column'] == mk['column']]
            same_col.sort(key=lambda m2: m2['y0'])
            i2 = same_col.index(mk)
            y1 = same_col[i2 + 1]['y0'] if i2 + 1 < len(same_col) else pix.height

            x0 = 0 if mk['column'] == 0 else pix.width // 2
            x1 = pix.width // 2 if mk['column'] == 0 else pix.width
            clip_img = img.crop((x0, mk['y0'] - 20, x1, y1))

            img_name = f'{Path(pdf_path).stem}_{pno:04d}_{mk["number"]}.png'
            img_path = str(Path(out_dir) / img_name)
            clip_img.save(img_path)

            text = pytesseract.image_to_string(clip_img, lang='kor+eng', config='--psm 6')

            results.append(OcrProblem(
                number=mk['number'],
                section_name=current_section,
                subsection_name=current_subsection,
                type_seq=max(type_seq, 1),
                type_hint=None,
                page_index=pno,
                image_path=img_path,
                text=text,
            ))

    doc.close()
    return results


if __name__ == '__main__':
    import sys
    pdf_path = sys.argv[1]
    out_dir = sys.argv[2]
    section_names = sys.argv[3].split(',')
    problems = extract_problems(pdf_path, out_dir, section_names)
    print('총 문제 수:', len(problems))
    from collections import Counter
    print('대단원별:', dict(Counter(p.section_name for p in problems)))
    print('소단원 수:', len(set(p.subsection_name for p in problems)))
