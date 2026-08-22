"""
"내신고쟁이" 계열 PDF 유형서(대수/미적분Ⅰ/확률과 통계 등)에서
대단원(Section) / 소단원(SubSection) 구조를 추출한다.

이 시리즈 PDF는 HWP 유형서와 달리 문제마다 이름 붙은 "유형"이 없고,
대단원 도입부(divider) 페이지에 큰 폰트로 대단원명이, 그 아래 작은
폰트 + 2자리 번호 조합으로 소단원 목록이 나온다. 실제 문제는 소단원
안에서 난이도 단계(핵심/심화/최고난도 유형)로만 묶인다 —
그 축은 models.DifficultyTier로 별도 관리한다.

** 아직 신뢰도가 낮은 실험 코드다. ** 폰트 크기만으로 대단원/소단원
번호를 구분하는데, 페이지 안에 같은 크기대의 텍스트가 여러 군데(현재
단원 도입부 외에 다음 단원 예고 등)에 나오면서 제목-번호 쌍이 엇갈리는
경우가 확인됐다. 지금은 seed_curriculum_taxonomy.py로 교육과정 기준
단원 구조를 직접 넣고 있고, 이 모듈은 그걸 대체할 만큼 안정적이지
않다 — 좌표 기반 페이지 레이아웃 분석(같은 페이지 안에서만 제목/번호를
짝짓기 등)으로 더 다듬어야 실사용 가능.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz

DIVIDER_MIN_SIZE_STRICT = 33.0  # 대단원 제목 폰트 크기 임계값(관찰치: ~35pt)
SUBSECTION_NO_SIZE = 25.0  # 소단원 번호 폰트 크기 임계값(관찰치: ~30pt, 대단원 제목보다 작음)
_NO_RE = re.compile(r'^\d{1,2}$')


@dataclass
class SubSectionEntry:
    no: str
    title: str


@dataclass
class SectionEntry:
    title: str
    subsections: list[SubSectionEntry] = field(default_factory=list)


def _line_spans(page):
    """페이지의 텍스트 조각을 (텍스트, 폰트크기) 단위로, 화면에 보이는
    순서(위->아래, 왼쪽->오른쪽)로 낸다. 제목과 번호가 같은 줄(line)에
    같이 놓여 크기가 섞이는 경우가 있어 span 단위로 쪼갠다."""
    d = page.get_text('dict')
    spans = []
    for block in d['blocks']:
        if 'lines' not in block:
            continue
        for line in block['lines']:
            for s in line['spans']:
                text = s['text'].strip()
                if not text:
                    continue
                x0, y0, x1, y1 = s['bbox']
                spans.append((y0, x0, text, s['size']))
    spans.sort(key=lambda t: (round(t[0]), t[1]))
    for y0, x0, text, size in spans:
        yield text, size


def extract_sections(pdf_path: str) -> list[SectionEntry]:
    doc = fitz.open(pdf_path)
    sections: list[SectionEntry] = []
    current: SectionEntry | None = None
    pending_title_parts: list[str] = []
    pending_sub_title: str | None = None

    for pno in range(doc.page_count):
        page = doc[pno]
        for text, size in _line_spans(page):
            # 순수 1~2자리 숫자(소단원 번호, ~30pt)를 최우선으로 판별한다.
            # 대단원 제목 폰트(~35pt)와 크기대가 겹치므로 숫자 패턴이 있으면
            # 무조건 번호로 취급한다.
            if SUBSECTION_NO_SIZE <= size < DIVIDER_MIN_SIZE_STRICT and _NO_RE.match(text):
                if current is not None and pending_sub_title:
                    current.subsections.append(
                        SubSectionEntry(no=text, title=pending_sub_title))
                pending_sub_title = None
                continue

            if size >= DIVIDER_MIN_SIZE_STRICT:
                # 대단원 제목은 페이지 안에서 여러 줄로 쪼개져 나온다
                pending_title_parts.append(text)
                continue
            if pending_title_parts:
                current = SectionEntry(title=''.join(pending_title_parts))
                sections.append(current)
                pending_title_parts = []

            # 소단원 제목 후보: 대단원 제목과 소단원 번호 "사이"에 나오는
            # 15~20pt 대의 한 줄짜리 한글 텍스트
            if current is not None and 14.0 <= size <= 20.0 and any('가' <= c <= '힣' for c in text):
                pending_sub_title = text

    doc.close()
    return sections


if __name__ == '__main__':
    import sys
    for p in sys.argv[1:]:
        print(f'=== {p} ===')
        for sec in extract_sections(p):
            print(sec.title)
            for sub in sec.subsections:
                print(f'  {sub.no} {sub.title}')
