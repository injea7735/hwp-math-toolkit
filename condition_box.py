"""문제 지문에 흔한 "(가) ... (나) ... (다) ..." 조건 나열을 찾아서
본문과 분리한다 (렌더러들이 이걸 박스로 감싸서 보여주는 데 쓴다)."""
from __future__ import annotations
import re

_MARKER_RE = re.compile(r'\(([가나다라마바사아]{1})\)')


def split_condition_block(text: str) -> tuple[str, list[str] | None, str]:
    """text에서 (가)/(나)/(다).. 로 시작하는 조건 목록을 찾아
    (조건 앞부분 본문, [조건1, 조건2, ...], 조건 뒤에 이어지는 본문) 으로
    나눈다. 각 조건 항목은 다음 마커나 줄바꿈 중 먼저 오는 지점에서 끝난다 —
    실제 문제는 흔히 "(가) ... (나) ...\n실제 질문(...)?" 처럼 조건 목록
    바로 뒤에 개행으로 구분된 실제 질문 문장이 이어지는데, 그 문장까지
    조건 항목에 같이 삼켜지면 안 되기 때문이다. 조건 표시가 하나도 없으면
    (text, None, "")을 그대로 반환한다."""
    matches = list(_MARKER_RE.finditer(text))
    if not matches:
        return text, None, ""

    main_text = text[:matches[0].start()].rstrip()
    items = []
    last_end = len(text)
    for i, m in enumerate(matches):
        next_marker = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        newline_pos = text.find('\n', m.end())
        end = min(next_marker, newline_pos) if newline_pos != -1 else next_marker
        items.append(text[m.start():end].strip())
        last_end = end
    trailing = text[last_end:].strip()
    return main_text, items, trailing
