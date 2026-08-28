import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PIL import Image, ImageDraw

from extract_sen_difficulty_badges import classify_band


def _band_with(pills):
    """(x, y, w, h, color) 목록을 흰 배경 45x400 RGB 배열에 그려서 반환."""
    img = Image.new('RGB', (400, 45), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for x, y, w, h, color in pills:
        draw.ellipse([x, y, x + w, y + h], fill=color)
    return np.array(img)


def test_no_pill_returns_none_and_default_kind():
    band = _band_with([])
    difficulty, kind = classify_band(band)
    assert difficulty is None
    assert kind == '객관식'


def test_orange_pill_is_ha():
    band = _band_with([(150, 8, 25, 25, (240, 165, 90))])
    difficulty, kind = classify_band(band)
    assert difficulty == '하'
    assert kind == '객관식'


def test_blue_pill_is_jung():
    band = _band_with([(150, 8, 25, 25, (140, 155, 210))])
    difficulty, kind = classify_band(band)
    assert difficulty == '중'


def test_pink_pill_is_sang():
    band = _band_with([(150, 8, 25, 25, (247, 107, 128))])
    difficulty, kind = classify_band(band)
    assert difficulty == '상'


def test_pill_left_of_number_area_ignored():
    # 대표문제 배지처럼 왼쪽(xmin<110)에 찍힌 색은 난이도로 오인하면 안 된다.
    band = _band_with([(20, 8, 25, 25, (240, 165, 90))])
    difficulty, kind = classify_band(band)
    assert difficulty is None


def test_essay_badge_detected_alongside_difficulty():
    band = _band_with([
        (150, 8, 25, 25, (140, 155, 210)),
        (250, 8, 90, 25, (190, 160, 70)),
    ])
    difficulty, kind = classify_band(band)
    assert difficulty == '중'
    assert kind == '서술형'


def test_essay_badge_alone_without_difficulty_pill():
    band = _band_with([(250, 8, 90, 25, (190, 160, 70))])
    difficulty, kind = classify_band(band)
    assert difficulty is None
    assert kind == '서술형'
