"""
쎈수학 미적분Ⅰ "문제.pdf"는 다른 쎈수학 과목들과 달리 소단원별 "대표문제"
HWP 인덱스 자료가 없다. 대신 각 대단원 시작부에 실제 유형 제목이 일반
검은 텍스트로 인쇄된 목차(TOC) 페이지가 있어서(초록 알약 폰트처럼 OCR이
안 되는 문제가 없다), 이 페이지들에서 소단원별 유형 번호+제목 순서 목록을
직접 뽑아 pdf_sen_extract.extract_problems()가 기대하는 "entries" 형식과
호환되게 만든다. problem_no/answer는 이 목차에 없으므로 빈 값으로 둔다 -
본문 크롭 순서(내부 순번 카운터)만으로 유형을 매칭한다.

대단원 목차 페이지는 옅은 민트색 소단원 헤더 박스(예: "01 함수의 극한")
+ 그 아래 "유형 NN 제목" 줄 목록으로 구성된다. 헤더 박스는 연결요소
색상 검출로 위치를 찾고, 그 아래 영역을 통째로 OCR해서 줄 단위로 판다.
수식이 섞인 제목(분수 등)은 OCR이 일부 깨질 수 있지만, "유형 NN" 순번
자체는 항상 안정적으로 읽힌다 - 순번이 본문 매칭에 쓰이는 값이고 제목은
참고용이므로 이 정도 오차는 허용한다.
"""
from __future__ import annotations

import re

import fitz
import numpy as np
import pytesseract
from PIL import Image
from scipy import ndimage

import os
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ.setdefault('TESSDATA_PREFIX', r'C:\Users\Ace\tessdata')

DPI = 150
_TYPE_LINE_RE = re.compile(r'유형\s*0*(\d+)[^\s\d]{0,2}\s+(.+)')


def _teal_header_boxes(arr: np.ndarray) -> list[tuple[int, int, int, int]]:
    r = arr[:, :, 0].astype(int); g = arr[:, :, 1].astype(int); b = arr[:, :, 2].astype(int)
    teal = (g > r + 10) & (g >= b - 10) & (r > 100) & (r < 200) & (g > 150)
    teal = ndimage.binary_dilation(teal, iterations=2)
    labels, _ = ndimage.label(teal, structure=np.ones((3, 3)))
    boxes = []
    for sl in ndimage.find_objects(labels):
        if sl is None:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        w, h = x1 - x0, y1 - y0
        if w > 80 and h > 15:
            boxes.append((x0, y0, w, h))
    return boxes


def _ocr(page, x0, y0, x1, y1, psm=6) -> str:
    rect = fitz.Rect(x0 * 72 / DPI, y0 * 72 / DPI, x1 * 72 / DPI, y1 * 72 / DPI)
    pix = page.get_pixmap(clip=rect, dpi=300)
    img = Image.frombuffer('RGB', (pix.width, pix.height), pix.samples, 'raw', 'RGB', 0, 1)
    return pytesseract.image_to_string(img, lang='kor', config=f'--psm {psm}')


def _page_type_lists(page) -> list[list[tuple[str, str]]]:
    """이 페이지의 유형 목록들을 (컬럼, y) 순서로 낸다 (헤더 알약 텍스트는 안 읽는다 -
    자체 폰트가 OCR에 잘 안 걸린다. 이름은 호출자가 알고 있는 순서로 매긴다)."""
    pix = page.get_pixmap(dpi=DPI)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    W = arr.shape[1]
    H_px = arr.shape[0]

    boxes = _teal_header_boxes(arr)
    by_col: dict[int, list[tuple[int, int, int, int]]] = {0: [], 1: []}
    for x0, y0, w, h in boxes:
        col = 0 if x0 < W / 2 else 1
        by_col[col].append((x0, y0, w, h))

    results = []
    for col in (0, 1):
        col_boxes = sorted(by_col[col], key=lambda b: b[1])
        col_x0 = 0 if col == 0 else W / 2
        col_x1 = W / 2 if col == 0 else W
        for i, (x0, y0, w, h) in enumerate(col_boxes):
            body_y0 = y0 + h
            body_y1 = col_boxes[i + 1][1] if i + 1 < len(col_boxes) else H_px
            body_text = _ocr(page, col_x0, body_y0, col_x1, body_y1, psm=6)

            types = []
            for line in body_text.splitlines():
                lm = _TYPE_LINE_RE.search(line)
                if lm is None:
                    continue
                types.append((lm.group(1).zfill(2), lm.group(2).strip()))
            results.append(types)
    return results


def parse_toc_pages(
    pdf_path: str, page_indices: list[int], subsection_names: list[str],
) -> dict[str, list[tuple[str, str]]]:
    """subsection_names는 목차에 나오는 소단원 실제 순서(=커리큘럼 순서)와
    정확히 같은 길이·순서여야 한다 - 헤더 알약 자체는 안 읽고 위치 순서로만 맞춘다."""
    doc = fitz.open(pdf_path)
    all_lists: list[list[tuple[str, str]]] = []
    for pno in page_indices:
        all_lists.extend(_page_type_lists(doc[pno]))
    doc.close()

    if len(all_lists) != len(subsection_names):
        raise ValueError(
            f'감지된 소단원 블록 수({len(all_lists)})가 예상({len(subsection_names)})과 다름'
        )
    result = dict(zip(subsection_names, all_lists))
    _apply_known_ocr_fixes(result)
    _check_no_gaps(result)
    return result


# 자동 OCR이 숫자 한 글자를 통째로 못 읽어서(예: "17"의 '7'이 사라져 "1?"로만
# 남고, 정규식은 남은 "1"만 번호로 잡아 엉뚱한 다른 유형과 번호가 겹침) 복구가
# 안 되는 극소수 줄만 수동으로 고친다 - 제목 텍스트로 그 줄을 찾아 번호만
# 바로잡는다(직접 페이지를 읽고 확인한 값). _check_no_gaps가 이 목록에 없는
# 새로운 구멍은 계속 잡아낸다.
_KNOWN_OCR_FIXES: dict[str, list[tuple[str, str]]] = {
    '도함수의 활용 ⑶': [('시각에 대한 길이의 변화율', '17')],
}


def _apply_known_ocr_fixes(result: dict[str, list[tuple[str, str]]]) -> None:
    for name, title_to_correct_no in _KNOWN_OCR_FIXES.items():
        types = result.get(name)
        if types is None:
            continue
        for title_text, correct_no in title_to_correct_no:
            result[name] = [
                (correct_no, title) if title == title_text else (no, title)
                for no, title in types
            ]
            types = result[name]
        result[name] = sorted(types, key=lambda t: int(t[0]))


def _check_no_gaps(result: dict[str, list[tuple[str, str]]]) -> None:
    """OCR이 줄 하나를 통째로 놓치면(글자가 아예 안 잡히는 경우) 순번에 구멍이
    생긴다 - 이건 제목 오타 정도가 아니라 본문 매칭용 소단원별 유형 개수 자체가
    틀어지는 심각한 문제이므로, 조용히 넘어가지 않고 바로 알아챌 수 있게 한다."""
    for name, types in result.items():
        nums = [int(no) for no, _ in types]
        expected = list(range(1, len(nums) + 1))
        if nums != expected:
            missing = sorted(set(expected) - set(nums))
            raise ValueError(f'{name}: 유형 순번에 구멍 발견 (빠진 번호: {missing}) - OCR 줄 누락 의심')


if __name__ == '__main__':
    import sys
    pdf_path = sys.argv[1]
    page_indices = [int(x) for x in sys.argv[2].split(',')]
    subsection_names = sys.argv[3].split(',')
    result = parse_toc_pages(pdf_path, page_indices, subsection_names)
    with open('mi1_toc_dump.txt', 'w', encoding='utf-8') as f:
        for name, types in result.items():
            f.write(f'=== {name} ({len(types)}) ===\n')
            for no, title in types:
                f.write(f'  유형{no}\t{title}\n')
    print('done, see mi1_toc_dump.txt')
