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


def test_strips_leading_20004_artifact():
    # DB 전체 651건 중 34건에서 "to [[NGD:...]]" 바로 앞에 항상 동일한
    # 숫자 "20004"가 붙어 나온다 - 서로 무관한 문제들에 우연히 같은 숫자가
    # 등장할 리 없으므로 추출 파이프라인이 남긴 잔여 아티팩트로 보고 같이 벗긴다.
    text = "점 $P 20004 to [[NGD:gtd340400]]$까지의 거리"
    assert strip_watermark_noise(text) == "점 $P$까지의 거리"


def test_other_numbers_before_to_are_not_stripped():
    # "20004"가 아닌 다른 숫자는 실제 수식 내용일 수 있으니 건드리면 안 된다.
    text = "$x 20005 to [[NGD:gtd340400]]$"
    assert strip_watermark_noise(text) == "$x 20005$"
