import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_sen_extract import (
    _find_colored_boxes, _find_green_boxes, _find_red_boxes, _is_type_pill, _is_daepyo_pill,
    _is_concept_heading, _resync_current_type, _save_trimmed,
)
from hwp_sen_daepyo_parse import RepresentativeType


def _white_canvas(h=100, w=100):
    return np.full((h, w, 3), 255, dtype=np.uint8)


def test_picks_most_saturated_pixel_not_center():
    # 컴포넌트 중앙이 흰 배경과 섞인 옅은 픽셀이어도(안티에일리어싱 등),
    # 그 부품 안의 진짜 원색(채도가 가장 높은 픽셀)을 대표색으로 써야 한다 -
    # 중앙 픽셀만 보면 (107,186,115) 같은 진짜 초록 대신 (152,205,202)처럼
    # 옅은 색을 잘못 대표색으로 골라서 유형 알약 색 판정에 실패했었다.
    arr = _white_canvas()
    arr[20:55, 20:83] = (107, 186, 115)  # 63x35 진짜 초록 알약
    arr[36, 51] = (152, 205, 202)  # 정중앙 픽셀만 옅은 색으로 오염

    boxes = _find_colored_boxes(arr)
    assert len(boxes) == 1
    x, y, w, h, color = boxes[0]
    assert (w, h) == (63, 35)
    assert color == (107, 186, 115)
    assert _is_type_pill(boxes[0])


def test_daepyo_pill_color_classified_correctly():
    arr = _white_canvas(h=60, w=200)
    arr[10:39, 10:146] = (239, 120, 83)  # 136x29 빨강 대표문제 알약

    boxes = _find_colored_boxes(arr)
    assert len(boxes) == 1
    assert _is_daepyo_pill(boxes[0])
    assert not _is_type_pill(boxes[0])


def test_small_noise_speck_is_not_a_type_pill():
    arr = _white_canvas()
    arr[10:13, 10:13] = (107, 186, 115)  # 3x3 잡음 - 알약 크기가 아님

    boxes = _find_colored_boxes(arr)
    assert not any(_is_type_pill(b) for b in boxes)


def test_green_pill_adjacent_to_gold_tag_not_contaminated():
    # 유형 알약 오른쪽에는 항상 금색 "개념 NN-N" 표찰이 붙어 있다. 둘이
    # 맞닿아 한 컴포넌트로 뭉치면 대표색이 금색 쪽으로 오염될 수 있었다
    # (실제로 (224,222,134) 같은 색이 나와서 유형 알약으로 인식 못 했음).
    # 마스크 단계에서부터 초록/빨강을 분리하면 이 오염이 원천 차단돼야 한다.
    arr = _white_canvas(h=100, w=250)
    arr[20:55, 20:83] = (78, 167, 123)  # 초록 유형 알약
    arr[25:40, 83:140] = (222, 180, 90)  # 바로 붙은 금색 "개념" 표찰

    green_boxes = _find_green_boxes(arr)
    pill_boxes = [b for b in green_boxes if _is_type_pill(b)]
    assert len(pill_boxes) == 1
    x, y, w, h, color = pill_boxes[0]
    assert (w, h) == (63, 35)  # 표찰까지 뭉쳐서 커지지 않았다
    assert color == (78, 167, 123)


def test_pale_green_pill_still_detected():
    # 렌더링 편차로 채도가 낮게 나오는 인스턴스도 있다(예: (163,198,112),
    # g-r=35) - 완전히 흰색과 섞인 극단적 경우가 아니면 잡아야 한다.
    arr = _white_canvas()
    arr[20:55, 20:83] = (163, 198, 112)

    boxes = _find_green_boxes(arr)
    assert any(_is_type_pill(b) for b in boxes)


def test_red_boxes_excludes_green_pill():
    arr = _white_canvas(h=60, w=200)
    arr[10:39, 10:146] = (239, 120, 83)  # 빨강 대표문제 알약
    arr[10:45, 150:213] = (78, 167, 123)  # 같은 페이지의 초록 유형 알약

    red_boxes = _find_red_boxes(arr)
    assert len(red_boxes) == 1
    assert _is_daepyo_pill(red_boxes[0])


def _entries():
    return [
        RepresentativeType(type_no='13', title='모평균과 표본평균의 차', problem_no='0692'),
        RepresentativeType(type_no='14', title='신뢰구간의 성질', problem_no='0694'),
        RepresentativeType(type_no='15', title='표본비율의 확률', problem_no='0697'),
    ]


def test_resync_corrects_counter_drift_from_ocr():
    # 실제 발생했던 버그: 유형 알약 하나를 색상 오검출로 놓쳐서 내부 순번
    # 카운터가 한 칸 밀렸다 - 대표문제 알약이 실제로는 '0694'(유형14)인데
    # 카운터는 여전히 '유형13'(0692)을 가리키고 있었다. 대표문제 OCR이
    # 0694를 읽으면 그게 진짜 유형14라고 보고 되돌려줘야 한다.
    entries = _entries()
    wrong_guess = entries[0]  # 카운터가 잘못 가리키는 유형13

    corrected = _resync_current_type(entries, wrong_guess, '0694')

    assert corrected is entries[1]
    assert corrected.title == '신뢰구간의 성질'


def test_resync_no_change_when_ocr_matches_current_guess():
    entries = _entries()
    assert _resync_current_type(entries, entries[1], '0694') is None


def test_resync_no_change_when_ocr_unreadable_or_unmatched():
    entries = _entries()
    assert _resync_current_type(entries, entries[0], '') is None
    assert _resync_current_type(entries, entries[0], '12') is None  # 4자리 아님
    assert _resync_current_type(entries, entries[0], '9999') is None  # 매칭 없음


def test_concept_heading_detected_by_amber_color_not_daepyo():
    # "04-4 독립시행의 확률" 같은 개념 소제목 알약: 진한 주황(대표문제 빨강과
    # 다름 - g-b 차이가 훨씬 큼), 크기는 유형 알약과 비슷하다.
    arr = _white_canvas(h=60, w=100)
    arr[10:47, 10:74] = (250, 155, 28)

    boxes = _find_red_boxes(arr)
    assert len(boxes) == 1
    assert _is_concept_heading(boxes[0])
    assert not _is_daepyo_pill(boxes[0])
    assert not _is_type_pill(boxes[0])


class _FakePixmap:
    def __init__(self, arr):
        self.height, self.width, self.n = arr.shape
        self.samples = arr.tobytes()
        self.saved_full = False

    def save(self, path):
        self.saved_full = True


def test_save_trimmed_cuts_trailing_blank_space(tmp_path):
    arr = np.full((400, 100, 3), 255, dtype=np.uint8)
    arr[20:60, 10:90] = 0  # 내용은 위쪽 20~60행에만 있고 나머지는 흰 여백
    pix = _FakePixmap(arr)
    out = tmp_path / 'out.png'

    _save_trimmed(pix, str(out), bottom_pad=25, min_height=60)

    from PIL import Image
    with Image.open(out) as saved:
        height = saved.height
    assert height < 200  # 400행 전체가 아니라 내용 근처(59+25=84)에서 잘렸다
    assert height == 84


def test_save_trimmed_ignores_thin_vertical_line_artifact(tmp_path):
    # 실제로 겪은 버그: 렌더링 잡음으로 크롭 전체 세로에 옅은 선 하나가
    # 쭉 이어지면(한 줄에 몇 픽셀뿐) "내용 있음"으로 잘못 잡혀서 거의
    # 안 잘렸다. 진짜 내용(20~60행, 폭 80픽셀)만 있고 그 아래는 잡음
    # 뿐이면 잡음은 무시하고 진짜 내용 근처에서 잘라야 한다.
    arr = np.full((400, 100, 3), 255, dtype=np.uint8)
    arr[20:60, 10:90] = 0  # 진짜 내용
    arr[60:400, 50:53] = 0  # 페이지 끝까지 이어지는 옅은 세로선 잡음(폭 3px)
    pix = _FakePixmap(arr)
    out = tmp_path / 'out.png'

    _save_trimmed(pix, str(out), bottom_pad=25, min_height=60, min_row_pixels=12)

    from PIL import Image
    with Image.open(out) as saved:
        height = saved.height
    assert height < 200  # 잡음 때문에 400행 끝까지 안 끌려갔다


def test_save_trimmed_keeps_minimum_height_for_short_content(tmp_path):
    arr = np.full((400, 100, 3), 255, dtype=np.uint8)
    arr[20:25, 10:90] = 0  # 아주 짧은 내용
    pix = _FakePixmap(arr)
    out = tmp_path / 'out.png'

    _save_trimmed(pix, str(out), bottom_pad=25, min_height=60)

    from PIL import Image
    with Image.open(out) as saved:
        height = saved.height
    assert height >= 60
