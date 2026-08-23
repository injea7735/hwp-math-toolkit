"""
"개념원리 RPM" 계열 PDF(미적분Ⅱ 등)에서 문제를 소단원 단위로 추출한다.

이 PDF는 텍스트도 임베드 이미지도 없이 페이지 전체가 벡터 그림(글자 하나하나가
경로로 그려짐)이라 렌더링 후 이미지 취급을 해야 한다.

** 개별 문제 번호 경계도, 유형 그룹(색깔 박스) 경계도 여러 방식으로
시도했지만(픽셀 밴드, 색상 매칭) 페이지의 다른 배경 요소와 계속 섞여
안정적으로 못 잡았다 - 그래서 이 두 단계는 포기하고, 확실하게 되는
두 가지만 쓴다:
  1. 대단원/소단원 경계: 앞쪽 "차례"(목차) 페이지에 정확한 인쇄 페이지
     번호가 나와 있어(예: "01 수열의 극한 006"), 범위를 그대로
     하드코딩한다(TOC 상수). 인쇄 페이지 번호와 PDF 페이지 인덱스는
     +1 차이(인쇄 "006" = PDF 인덱스 5)로 확인했다.
  2. 문제 페이지 판별: "교과서 문제 정복하기" 헤더가 있는 페이지만
     번호 매겨진 문제가 있다(개념 설명 페이지는 제외).

결과적으로 소단원 하나 = Problem 하나(image_paths에 그 소단원의 문제
페이지들을 전부 담음)로 저장한다. 개별 문제/유형 단위 분리는 나중에
다른 방법(레이아웃 분석 라이브러리 등)으로 다시 시도해야 한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ.setdefault('TESSDATA_PREFIX', r'C:\Users\Ace\tessdata')

DPI = 200

TOC = [
    ('수열의 극한', '수열의 극한', 6),
    ('수열의 극한', '급수', 24),
    ('미분법', '지수함수와 로그함수의 미분', 42),
    ('미분법', '삼각함수의 미분', 56),
    ('미분법', '여러 가지 미분법', 72),
    ('미분법', '도함수의 활용 ⑴', 86),
    ('미분법', '도함수의 활용 ⑵', 104),
    ('적분법', '여러 가지 적분법', 124),
    ('적분법', '정적분', 134),
    ('적분법', '정적분의 활용', 152),
]
PRINTED_PAGE_TO_INDEX_OFFSET = -1
LAST_SECTION_END_PRINTED_PAGE = 168


@dataclass
class RpmSubsectionGroup:
    section_name: str
    subsection_name: str
    image_paths: list[str] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)


def _subsection_ranges() -> list[tuple[str, str, int, int]]:
    ranges = []
    for i, (section, subsection, printed_start) in enumerate(TOC):
        start_idx = printed_start + PRINTED_PAGE_TO_INDEX_OFFSET
        if i + 1 < len(TOC):
            next_start = TOC[i + 1][2] + PRINTED_PAGE_TO_INDEX_OFFSET
        else:
            next_start = LAST_SECTION_END_PRINTED_PAGE + PRINTED_PAGE_TO_INDEX_OFFSET
        ranges.append((section, subsection, start_idx, next_start))
    return ranges


def _is_problem_page(page) -> bool:
    rect = page.rect
    clip = fitz.Rect(0, 0, rect.width, rect.height * 0.15)
    pix = page.get_pixmap(dpi=200, clip=clip)
    img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    text = pytesseract.image_to_string(img, lang='kor+eng', config='--psm 6')
    return '교과서' in text or '문제' in text


def extract_subsections(pdf_path: str, out_dir: str) -> list[RpmSubsectionGroup]:
    doc = fitz.open(pdf_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    groups = []
    for section_name, subsection_name, start_idx, end_idx in _subsection_ranges():
        group = RpmSubsectionGroup(section_name=section_name, subsection_name=subsection_name)
        for pno in range(max(0, start_idx), min(doc.page_count, end_idx)):
            page = doc[pno]
            if not _is_problem_page(page):
                continue
            pix = page.get_pixmap(dpi=DPI)
            img_name = f'{Path(pdf_path).stem}_{subsection_name}_{pno:04d}.png'
            img_path = str(Path(out_dir) / img_name)
            pix.save(img_path)
            group.image_paths.append(img_path)
            group.text_parts.append(page.get_text())
        if group.image_paths:
            groups.append(group)

    doc.close()
    return groups


if __name__ == '__main__':
    import sys

    pdf_path = sys.argv[1]
    out_dir = sys.argv[2]
    groups = extract_subsections(pdf_path, out_dir)
    print('총 소단원 수:', len(groups))
    for g in groups:
        print(g.subsection_name, len(g.image_paths), '페이지')
