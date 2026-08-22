"""검색/분류 같은 파생 텍스트 분석에서 쓸 정규화 유틸리티.

주의: 저장된 원본 문제 데이터(Problem.stem_latex 등)는 절대 건드리지 않는다.
여기 함수는 그 원본에서 분석용으로 따로 뽑아낸 사본에만 적용한다 — NGD가 심어둔
[[NGD:...]] 워터마크 토큰은 실제 수식 내용이 아니라서, 키워드 추출이나 자동
유형분류 같은 분석 로직에 노이즈로 섞여 들어가면 결과가 왜곡되기 때문.
"""
from __future__ import annotations
import re

_WATERMARK_TOKEN = re.compile(r"\[\[NGD:[^\]]*\]\]")


def strip_watermark_noise(text: str) -> str:
    """분석용 텍스트 사본에서 NGD 워터마크 토큰만 제거해 반환한다."""
    return _WATERMARK_TOKEN.sub("", text)
