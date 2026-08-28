"""문제 지문에 흔한 "(가) ... (나) ... (다) ..." 조건 나열을 찾아서
본문과 분리한다 (렌더러들이 이걸 박스로 감싸서 보여주는 데 쓴다)."""
from __future__ import annotations
import re

_MARKER_RE = re.compile(r'\(([가나다라마바사아]{1})\)')


def split_condition_block(text: str) -> tuple[str, list[str] | None]:
    """text에서 (가)/(나)/(다).. 로 시작하는 조건 목록을 찾아
    (조건 앞부분 본문, [조건1, 조건2, ...]) 로 나눈다. 조건 표시가 하나도
    없으면 (text, None)을 그대로 반환한다."""
    matches = list(_MARKER_RE.finditer(text))
    if not matches:
        return text, None

    main_text = text[:matches[0].start()].rstrip()
    items = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        items.append(text[m.start():end].strip())
    return main_text, items
