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

import hashlib
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

# "STEP 1/2/3" 난이도 배너는 본문 텍스트가 아니라 그림(BinData)으로 박혀
#있다 - 같은 "내신고쟁이" 시리즈 안에서는 완전히 같은 이미지 파일이
# 파일마다 다른 BinData 번호로 재사용되므로, 내용의 md5로 식별한다(직접
# 여러 소단원 파일에서 md5가 동일함을 확인함).
_STEP_TIER_HASHES = {
    '09cc38465bc640d2b7b77a5430109280': 'STEP1',
    '7da65629d04b9cbb5b6b6208e780a979': 'STEP2',
    '5301bc21812743c11b4dcf251ba4400e': 'STEP3',
}


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
    tier: str | None = None  # 이 문제 앞에 마지막으로 나온 STEP 배너("STEP1"/"STEP2"/"STEP3")


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


def _in_endnote(el: etree._Element) -> bool:
    for anc in el.iterancestors():
        if anc.tag == 'EndNote':
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


def _bindata_md5(ole: olefile.OleFileIO, bindata_id: int) -> str | None:
    for ext in ('bmp', 'png', 'jpg', 'gif'):
        name = f'BIN{bindata_id:04X}.{ext}'
        if ole.exists(['BinData', name]):
            raw = ole.openstream(['BinData', name]).read()
            try:
                data = zlib.decompress(raw, -15)
            except zlib.error:
                data = raw
            return hashlib.md5(data).hexdigest()
    return None


def _step_tier_in(el: etree._Element, ole: olefile.OleFileIO, cache: dict) -> str | None:
    """el(GShapeObjectControl) 안에 STEP 배너 그림이 있으면 그 등급을 반환한다."""
    for pic in el.iter('PictureInfo'):
        bindata_id = pic.get('bindata-id')
        if bindata_id is None:
            continue
        bindata_id = int(bindata_id)
        if bindata_id not in cache:
            cache[bindata_id] = _bindata_md5(ole, bindata_id)
        tier = _STEP_TIER_HASHES.get(cache[bindata_id])
        if tier:
            return tier
    return None


def extract_problems(path: str) -> list[Problem]:
    """유형별 문제 본문을 수식 포함해서 재구성한다.

    한 문제는 본문 흐름에서 다음 패턴으로 나타난다:
      AutoNumbering(번호) -> "정답" + 답 -> 문단 끝(\\r) -> 문제 지문
      (Text/EqEdit이 섞여 나옴) -> ... -> 다음 AutoNumbering
    수식(EqEdit)은 원본 레코드 스트림에서 등장 순서대로 미리 뽑아 둔 뒤,
    XML 트리를 훑으면서 EqEdit 자리가 나올 때마다 하나씩 꺼내 LaTeX로
    바꿔 그 자리에 $...$ 로 끼워 넣는다. 두 추출 방식 모두 같은 레코드
    스트림을 순서대로 훑으므로 EqEdit 등장 순서가 서로 맞아떨어진다.

    **"정답" 뒤에 붙는 건 사실 답 기호 하나가 아니라 EndNote(각주) 전체다**
    - 실제로 원본 파일을 열어 XML 트리를 직접 걸어보고 확인함: AutoNumbering
    바로 뒤의 " 정답 "/"③" 같은 Text도, 그 뒤에 이어지는 여러 줄짜리 전체
    풀이 과정(수식 포함)도 전부 `<EndNote>` 태그 아래에 들어 있다 - 인쇄/
    화면에는 안 보이지만(각주라서) 문서 파일 안에는 그대로 남아 있는
    "숨은 해설"이다. 기존 코드는 이 경계를 문단 끝(\\r) 하나로만 판단했는데,
    풀이가 여러 문단(=여러 \\r)에 걸쳐 있다 보니 첫 \\r 이후의 나머지
    풀이 내용이 in_answer_zone=False 상태에서 그대로 stem_parts로 흘러들어가
    실제 문제 지문 앞에 풀이가 통째로 붙는 심각한 버그가 있었다(2026-08-29
    발견 - 이미 들어간 883+690개 행 중 상당수가 이 상태로 저장되어 있었음,
    별도로 재수입해서 복구함). 지금은 문단 끝이 아니라 `_in_endnote(el)`로
    직접 판단한다 - EndNote를 벗어난 뒤에 나오는 Text/EqEdit만 진짜
    stem_parts로 들어간다.
    """
    root = _xml_root(path)
    equations = iter(extract_equation_scripts(path))
    ole = olefile.OleFileIO(path)
    step_hash_cache: dict[int, str | None] = {}

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
    current_tier: str | None = None
    type_seq = 0

    cur_no: str | None = None
    problem_tier: str | None = None  # 지금 진행 중인 문제가 시작될 때의 tier 스냅샷
    in_answer_zone = False
    answer_parts: list[str] = []
    stem_parts: list[str] = []

    def flush():
        # current_tier를 flush 시점에 바로 읽으면 안 된다 - 문제 본문이 끝나고
        # 다음 AutoNumbering이 나오기 전에 STEP 배너를 먼저 만나면(예: 소단원
        # 마지막 문제 뒤에 다음 섹션의 빈 STEP 배너가 곧바로 이어지는 경우)
        # 방금 끝난 문제가 아직 시작도 안 한 다음 tier로 잘못 태깅된다.
        # 그래서 문제가 "시작될 때" 캡처해 둔 problem_tier를 대신 쓴다.
        nonlocal cur_no, answer_parts, stem_parts
        if cur_no is not None and current_type is not None:
            problems.append(Problem(
                type_no=current_type[0],
                type_title=current_type[1],
                seq=type_seq,
                answer=''.join(answer_parts).strip(),
                stem=''.join(stem_parts).strip(),
                tier=problem_tier,
            ))
        cur_no = None
        answer_parts = []
        stem_parts = []

    try:
        for el in root.iter():
            tag = el.tag
            if tag == 'GShapeObjectControl':
                tier = _step_tier_in(el, ole, step_hash_cache)
                if tier and tier != current_tier:
                    # 새 STEP 섹션 시작 - 이 시리즈는 STEP마다 같은 유형 제목
                    # (01, 02, ...)을 그대로 재사용하므로, seen_nos를 여기서
                    # 리셋 안 하면 STEP2의 첫 유형 제목이 STEP1의 반복으로
                    # 오인되어 "정답 섹션 시작"으로 잘못 종료된다. STEP 배너가
                    # 없는 책(seen_nos가 애초에 안 쓰이는 경우는 없지만, tier가
                    # 계속 None이면 이 분기 자체가 안 걸리므로 기존 동작은
                    # 그대로 보존된다.
                    seen_nos.clear()
                    current_tier = tier
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
                # 이 시리즈의 모든 소단원 파일은 항상 STEP1 문제로 시작한다
                # (확인됨) - 그런데 파일 한 개에서 STEP1 배너 그림이 다른
                # 파일들과 다른 바이트로 인코딩되어 있어(같은 "STEP1" 도안인데
                # 해시가 안 맞음) 배너 자체가 감지되지 않는 경우를 발견했다.
                # 아직 어떤 STEP 배너도 못 만난 상태에서 문제가 시작되면
                # STEP1으로 본다 - 임의 추측이 아니라 이 시리즈 전체에서
                # 확인된 문서 구조를 따르는 것이다.
                problem_tier = current_tier or 'STEP1'
                in_answer_zone = True
                continue

            if tag == 'ControlChar' and el.get('name') == 'PARAGRAPH_BREAK':
                if in_answer_zone:
                    in_answer_zone = False
                continue

            if cur_no is None:
                continue

            if tag == 'Text' and el.text:
                if in_answer_zone:
                    answer_parts.append(el.text)
                elif not _in_endnote(el):
                    stem_parts.append(el.text)
                # else: 정답 각주(EndNote) 안에서 첫 문단 구분(\r) 이후로
                # 이어지는 풀이 잔여 텍스트 - 버린다(아래 EndNote 설명 참고)
            elif tag == 'EqEdit':
                latex = next_latex()
                if in_answer_zone:
                    if latex:
                        answer_parts.append(f'${latex}$')
                elif not _in_endnote(el) and latex:
                    stem_parts.append(f'${latex}$')

        flush()
        return problems
    finally:
        ole.close()


if __name__ == '__main__':
    import sys
    for p in sys.argv[1:]:
        outline = extract_outline(p)
        print(f'=== {p} ===')
        print('unit:', outline.unit_title)
        for t in outline.types:
            print(f'  {t.no} {t.title} ({t.problem_count}문제 추정)')
