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
