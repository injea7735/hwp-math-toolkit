"""쎈수학 문제 크롭 이미지 상단에 찍힌 하/중/상 난이도 배지와 서술형 배지를
찾아 Problem.difficulty_label / Problem.question_kind를 채운다.

문제 번호 오른쪽에 작은 원형 배지가 붙어있다(하=주황, 중=파랑, 상=분홍-빨강,
색은 실제 PDF에서 픽셀 샘플링으로 확인함). 서술형 문제는 그 옆에 폭이 넓은
황금색 "서술형" 배지가 추가로 붙는다. 대표문제(대표 문제 주황 막대 배지만
있음)는 난이도 배지가 아예 없다 - 못 찾으면 None으로 두고 절대 추측해서
채우지 않는다(이 프로젝트의 기존 "don't store a guess" 원칙과 동일).

주의: 흰 글자가 원 안에 있어 배지 전체를 하나의 연결 성분으로 잡으면 중심
픽셀이 흰 글자 위에 찍혀 색을 잘못 읽는다(고리 모양이라 centroid가 구멍
속에 옴) - 그래서 색은 centroid가 아니라 실제로 채도 조건을 통과한 픽셀들의
median으로 구한다.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

_BAND_HEIGHT = 45
_BAND_WIDTH = 460
# 이보다 왼쪽은 문제 번호나 "대표 문제" 배지 영역이라 제외한다. 번호 자릿수가
# 짧으면(예: "0064") 실제 난이도 배지가 x=107까지 당겨져 나오는 경우가 있어
# 110보다 살짝 낮춰서 여유를 둔다.
_PILL_XMIN = 100


def _difficulty_from_color(r: int, g: int, b: int) -> str | None:
    if r > 200 and 130 < g < 190 and 50 < b < 120 and r > g + 40:
        return '하'
    if 90 < r < 170 and 120 < g < 190 and 180 < b < 240 and b > r + 40:
        return '중'
    if r > 210 and 70 < g < 140 and 95 < b < 165 and r > g + 80:
        return '상'
    return None


def _is_essay_badge_color(r: int, g: int, b: int) -> bool:
    return 150 < r < 230 and 125 < g < 200 and 40 < b < 100


def _saturated_components(band: np.ndarray):
    """band(RGB 배열)에서 채도 있는 연결 성분들을 (x, y, w, h, median_r, g, b)로 반환."""
    r = band[:, :, 0].astype(int)
    g = band[:, :, 1].astype(int)
    b = band[:, :, 2].astype(int)
    sat_mask = (
        np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b) > 30
    ) & (np.maximum(np.maximum(r, g), b) > 90)
    labels, n = ndimage.label(sat_mask)
    for i in range(1, n + 1):
        ys, xs = np.where(labels == i)
        if len(xs) < 40:
            continue
        xmin, xmax = int(xs.min()), int(xs.max())
        ymin, ymax = int(ys.min()), int(ys.max())
        w, h = xmax - xmin + 1, ymax - ymin + 1
        rr = int(np.median(band[ys, xs, 0]))
        gg = int(np.median(band[ys, xs, 1]))
        bb = int(np.median(band[ys, xs, 2]))
        yield xmin, ymin, w, h, rr, gg, bb


def classify_band(band: np.ndarray) -> tuple[str | None, str]:
    """상단 배지 영역(RGB 배열)에서 (난이도_라벨_또는_None, question_kind)를 뽑는다.
    서술형 배지가 없으면 question_kind는 기존 파이프라인 기본값과 동일하게
    '객관식'을 반환한다(이 책들에 단답형을 구분하는 별도 배지는 없음 - 확인됨)."""
    difficulty = None
    question_kind = '객관식'
    for xmin, ymin, w, h, r, g, b in _saturated_components(band):
        if xmin < _PILL_XMIN:
            continue
        # 원형 난이도 배지: 지름 14~34px, 정사각형에 가까운 비율
        if difficulty is None and 14 <= w <= 34 and 14 <= h <= 34 and abs(w - h) <= 10:
            difficulty = _difficulty_from_color(r, g, b)
            if difficulty is not None:
                continue
        # 서술형 배지: 폭이 높이의 2.3배 이상인 넓은 막대
        if w >= 2.3 * h and _is_essay_badge_color(r, g, b):
            question_kind = '서술형'
    return difficulty, question_kind


def detect_badges(image_path: str) -> tuple[str | None, str]:
    """문제 크롭 이미지 파일에서 (난이도_라벨_또는_None, question_kind)를 뽑는다."""
    img = Image.open(image_path).convert('RGB')
    arr = np.array(img)
    band = arr[:_BAND_HEIGHT, : min(_BAND_WIDTH, arr.shape[1])]
    return classify_band(band)
