"""검색/분류 같은 파생 텍스트 분석에서 쓸 정규화 유틸리티.

주의: 저장된 원본 문제 데이터(Problem.stem_latex 등)는 절대 건드리지 않는다.
여기 함수는 그 원본에서 분석용으로 따로 뽑아낸 사본에만 적용한다 — NGD가 심어둔
[[NGD:...]] 워터마크 토큰은 실제 수식 내용이 아니라서, 키워드 추출이나 자동
유형분류 같은 분석 로직에 노이즈로 섞여 들어가면 결과가 왜곡되기 때문.
"""
from __future__ import annotations
import re

# NGD의 워터마크는 "실제 내용 to [[NGD:xxxxxxxx]]" 형태로, 바로 앞에 붙는
# 영단어 "to"까지 워터마크 삽입 메커니즘의 일부다(진짜 \to 화살표 변환은
# NGD 쪽에서 "->"로 쓰지 "to"라는 단어를 쓰지 않는다 - 실제 문제 다수에서
# 확인됨). 그래서 앞의 공백+to까지 같이 제거해야 "...전제to점]" 같은
# 지저분한 잔여물이 안 남는다.
_WATERMARK_TOKEN = re.compile(r"\s*to\s*\[\[NGD:[^\]]*\]\]|\[\[NGD:[^\]]*\]\]")


def strip_watermark_noise(text: str) -> str:
    """분석/표시용 텍스트 사본에서 NGD 워터마크 토큰(과 그 앞에 붙는 "to")을
    제거해 반환한다."""
    return _WATERMARK_TOKEN.sub("", text)
