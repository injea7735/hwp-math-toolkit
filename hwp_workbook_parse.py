"""
"유형서"(단원별로 유형이 나뉜 HWP 문제집) 파일에서 구조를 추출한다.

HWP 파일 안에서:
  - 유형 제목은 본문 문단이 아니라 별도의 텍스트박스(GShapeObjectControl)
    안에 들어 있고, 마지막 텍스트 런이 "01" 같은 2자리 번호로 분리되어 있다.
  - 수식은 BodyText 스트림에 HWPTAG_CTRL_EQEDIT(88) 레코드로 저장되며,
    hwp_eq_to_latex.py가 다루는 것과 같은 한글 수식 스크립트(DSL)가
    BSTR로 들어 있다. pyhwp의 상위 레벨 파서는 이 필드를 해석하지 않으므로
    레코드 스트림을 직접 걸어서 꺼낸다.
  - 문제 하나가 끝나면 "정답" 문단이 나오는 패턴을 이용해 유형별 문제 수를
    가늠한다(본문 텍스트 재구성 없이 개수만 세는 수준의 1차 구현).
"""
from __future__ import annotations

import io
import re
import struct
import zlib
from contextlib import closing
from dataclasses import dataclass, field

import olefile
from lxml import etree
from hwp5.xmlmodel import Hwp5File

from hwp_eq_to_latex import hwp_eq_to_latex

HWPTAG_CTRL_EQEDIT = 88

_TYPE_NO_RE = re.compile(r'^\d{1,2}$')


@dataclass
class TypeSection:
    no: str
    title: str
    problem_count: int = 0


@dataclass
class Problem:
    type_no: str
    type_title: str
    seq: int          # 유형 안에서 몇 번째 문제인지(1부터)
    answer: str        # "정답" 옆에 바로 나오는 값/기호
    stem: str          # 문제 본문. 수식은 $...$ 로 감싼 LaTeX로 들어간다.


@dataclass
class WorkbookOutline:
    source_path: str
    subject: str | None
    unit_title: str | None
    types: list[TypeSection] = field(default_factory=list)


def _xml_root(path: str) -> etree._Element:
    with closing(Hwp5File(path)) as h5:
        buf = io.BytesIO()
        h5.xmlevents(embedbin=False).dump(buf)
    buf.seek(0)
    return etree.parse(buf).getroot()


def _in_textbox(el: etree._Element) -> bool:
    for anc in el.iterancestors():
        if anc.tag == 'TextboxParagraphList':
            return True
    return False


def extract_outline(path: str) -> WorkbookOutline:
    """유형 제목 목록 + 유형별 대략적인 문제 수를 추출한다."""
    root = _xml_root(path)
    outline = WorkbookOutline(source_path=path, subject=None, unit_title=None)

    current: TypeSection | None = None
    seen_nos: set[str] = set()
    for el in root.iter():
        if el.tag == 'GShapeObjectControl':
            runs = [t.text for t in el.iter('Text') if t.text]
            if not runs:
                continue
            last = runs[-1].strip()
            if _TYPE_NO_RE.match(last):
                title = ''.join(runs[:-1]).strip()
                # 제목에 숫자가 섞여도 된다("미지수가 2개인 ...").
                # 대신 한글이 하나도 없는 경우(수식 조각 등)는 제외한다.
                if title and any('가' <= ch <= '힣' for ch in title):
                    if last in seen_nos:
                        # 문제 파트가 끝나고 정답/해설 파트가 같은 유형
                        # 제목을 반복하기 시작하는 지점 -> 여기서 멈춘다.
                        break
                    seen_nos.add(last)
                    current = TypeSection(no=last, title=title)
                    outline.types.append(current)
                    continue
            # 파일 맨 위 "01-평면좌표" 식의 단원 라벨
            joined = ''.join(runs).strip()
            m = re.match(r'^(\d{2})-(.+)$', joined)
            if m and outline.unit_title is None:
                outline.unit_title = m.group(2)
        elif el.tag == 'Text' and not _in_textbox(el):
            if el.text and '정답' in el.text and current is not None:
                current.problem_count += 1

    return outline


def _decode_bstr(payload: bytes, offset: int):
    if offset + 2 > len(payload):
        return None, offset
    length = struct.unpack_from('<H', payload, offset)[0]
    offset += 2
    nbytes = length * 2
    if offset + nbytes > len(payload):
        return None, offset
    text = payload[offset:offset + nbytes].decode('utf-16le', errors='replace')
    return text, offset + nbytes


def extract_equation_scripts(path: str) -> list[str]:
    """문서에 등장하는 순서대로 수식 DSL 스크립트를 추출한다.

    hwp_eq_to_latex.hwp_eq_to_latex()에 그대로 넣을 수 있는 문법이다.
    """
    ole = olefile.OleFileIO(path)
    try:
        raw = ole.openstream('BodyText/Section0').read()
    finally:
        ole.close()

    try:
        data = zlib.decompress(raw, -15)
    except zlib.error:
        data = raw

    scripts = []
    pos = 0
    n = len(data)
    while pos + 4 <= n:
        header = struct.unpack_from('<I', data, pos)[0]
        tagid = header & 0x3FF
        size = (header >> 20) & 0xFFF
        pos += 4
        if size == 0xFFF:
            size = struct.unpack_from('<I', data, pos)[0]
            pos += 4
        payload = data[pos:pos + size]
        pos += size
        if tagid == HWPTAG_CTRL_EQEDIT:
            script, _ = _decode_bstr(payload, 4)
            if script is not None:
                scripts.append(script)
    return scripts


def extract_problems(path: str) -> list[Problem]:
    """유형별 문제 본문을 수식 포함해서 재구성한다.

    한 문제는 본문 흐름에서 다음 패턴으로 나타난다:
      AutoNumbering(번호) -> "정답" + 답 -> 문단 끝(\\r) -> 문제 지문
      (Text/EqEdit이 섞여 나옴) -> ... -> 다음 AutoNumbering
    수식(EqEdit)은 원본 레코드 스트림에서 등장 순서대로 미리 뽑아 둔 뒤,
    XML 트리를 훑으면서 EqEdit 자리가 나올 때마다 하나씩 꺼내 LaTeX로
    바꿔 그 자리에 $...$ 로 끼워 넣는다. 두 추출 방식 모두 같은 레코드
    스트림을 순서대로 훑으므로 EqEdit 등장 순서가 서로 맞아떨어진다.
    """
    root = _xml_root(path)
    equations = iter(extract_equation_scripts(path))

    def next_latex() -> str:
        script = next(equations, None)
        if script is None:
            return ''
        try:
            return hwp_eq_to_latex(script)
        except Exception:
            return script  # 변환 실패 시 원본 스크립트라도 남긴다

    problems: list[Problem] = []
    seen_nos: set[str] = set()
    current_type: tuple[str, str] | None = None  # (no, title)
    type_seq = 0

    cur_no: str | None = None
    in_answer_zone = False
    answer_parts: list[str] = []
    stem_parts: list[str] = []

    def flush():
        nonlocal cur_no, answer_parts, stem_parts
        if cur_no is not None and current_type is not None:
            problems.append(Problem(
                type_no=current_type[0],
                type_title=current_type[1],
                seq=type_seq,
                answer=''.join(answer_parts).strip(),
                stem=''.join(stem_parts).strip(),
            ))
        cur_no = None
        answer_parts = []
        stem_parts = []

    for el in root.iter():
        tag = el.tag
        if tag == 'GShapeObjectControl':
            runs = [t.text for t in el.iter('Text') if t.text]
            for t in el.iter('EqEdit'):
                next_latex()  # 텍스트박스 안 수식도 큐에서 소비만 하고 버린다
            if not runs:
                continue
            last = runs[-1].strip()
            if _TYPE_NO_RE.match(last):
                title = ''.join(runs[:-1]).strip()
                if title and any('가' <= ch <= '힣' for ch in title):
                    if last in seen_nos:
                        flush()
                        return problems  # 정답/해설 파트 시작 -> 종료
                    seen_nos.add(last)
                    flush()
                    current_type = (last, title)
                    type_seq = 0
            continue

        if _in_textbox(el):
            continue

        if tag == 'AutoNumbering':
            flush()
            type_seq += 1
            cur_no = el.get('number') or str(type_seq)
            in_answer_zone = True
            continue

        if tag == 'ControlChar' and el.get('name') == 'PARAGRAPH_BREAK':
            if in_answer_zone:
                in_answer_zone = False
            continue

        if cur_no is None:
            continue

        if tag == 'Text' and el.text:
            (answer_parts if in_answer_zone else stem_parts).append(el.text)
        elif tag == 'EqEdit':
            latex = next_latex()
            if latex:
                (answer_parts if in_answer_zone else stem_parts).append(f'${latex}$')

    flush()
    return problems


if __name__ == '__main__':
    import sys
    for p in sys.argv[1:]:
        outline = extract_outline(p)
        print(f'=== {p} ===')
        print('unit:', outline.unit_title)
        for t in outline.types:
            print(f'  {t.no} {t.title} ({t.problem_count}문제 추정)')
