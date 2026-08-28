import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from text_normalize import strip_watermark_noise


def test_strips_watermark_token():
    text = r"x^\frac{2}{\left|x \right| to [[NGD:gtd340400]]}"
    assert "[[NGD:" not in strip_watermark_noise(text)


def test_leaves_other_text_untouched():
    text = r"\lim_{x\to\infty}{\sqrt{3x-9}}"
    assert strip_watermark_noise(text) == text


def test_strips_multiple_tokens():
    text = "[[NGD:aaa111]] 문제 본문 [[NGD:bbb222]]"
    assert strip_watermark_noise(text) == " 문제 본문 "


def test_strips_leading_to_artifact():
    # NGD 워터마크는 "... to [[NGD:xxx]]" 형태로 삽입되는데, 앞의 "to"도
    # 진짜 화살표 변환(NGD는 ->를 씀)이 아니라 워터마크 메커니즘의 일부다.
    text = "[4.7 to [[NGD:gtd340400]]점]"
    assert strip_watermark_noise(text) == "[4.7점]"


def test_real_to_arrow_not_stripped_without_watermark():
    text = r"\lim_{x\to\infty}{\sqrt{3x-9}}"
    assert strip_watermark_noise(text) == text
