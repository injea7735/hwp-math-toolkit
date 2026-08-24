import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_problem_extract import _group_number_spans


def _span(text, x0, y0, x1=None, y1=None):
    return {'text': text, 'bbox': (x0, y0, (x1 if x1 is not None else x0 + 10), (y1 if y1 is not None else y0 + 20))}


def test_same_row_different_columns_stay_separate():
    # 실제 자료에서 확인된 버그: 2단 레이아웃에서 왼쪽 열 "013"과 오른쪽 열
    # "016"이 같은 y좌표라는 이유만으로 "013016"으로 합쳐졌었다.
    page_width = 400.0
    spans = [
        _span('0', 42, 100), _span('13', 51, 100),    # 왼쪽 열, x < 200
        _span('0', 334, 100), _span('16', 343, 100),  # 오른쪽 열, x >= 200
    ]
    markers = _group_number_spans(spans, page_width)
    numbers = sorted(m[0] for m in markers)
    assert numbers == ['013', '016']


def test_multi_fragment_number_concatenated_by_x_order():
    spans = [_span('0', 42, 100), _span('0', 51, 100), _span('1', 60, 100)]
    markers = _group_number_spans(spans, page_width=400.0)
    assert markers[0][0] == '001'


def test_different_rows_stay_separate_markers():
    spans = [_span('0', 42, 100), _span('1', 51, 100), _span('0', 42, 300), _span('2', 51, 300)]
    markers = _group_number_spans(spans, page_width=400.0)
    numbers = sorted(m[0] for m in markers)
    assert numbers == ['01', '02']


def test_reading_order_left_column_then_right_column():
    page_width = 400.0
    spans = [
        _span('0', 42, 300), _span('2', 51, 300),    # 왼쪽 열, 아래
        _span('0', 42, 100), _span('1', 51, 100),    # 왼쪽 열, 위
        _span('0', 334, 200), _span('3', 343, 200),  # 오른쪽 열
    ]
    markers = _group_number_spans(spans, page_width)
    assert [m[0] for m in markers] == ['01', '02', '03']
