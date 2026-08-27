import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_mi1_toc_parse import _TYPE_LINE_RE, _apply_known_ocr_fixes, _check_no_gaps


def test_type_line_regex_matches_clean_line():
    # 정규식 자체는 앞자리 0을 소비한다 - 실제 호출부(_page_type_lists)가
    # 뒤에서 .zfill(2)로 되돌린다.
    m = _TYPE_LINE_RE.search('유형01 함수의 극한값의 존재')
    assert m.group(1) == '1'
    assert m.group(2) == '함수의 극한값의 존재'


def test_type_line_regex_tolerates_ocr_junk_after_number():
    # OCR이 번호와 제목 사이에 잡음 글자를 하나 끼워 넣는 경우
    m = _TYPE_LINE_RE.search('유형 05, 함수의 극한에 대한 성질')
    assert m.group(1) == '5'


def test_check_no_gaps_passes_for_contiguous_sequence():
    result = {'함수의 극한': [('01', 'a'), ('02', 'b'), ('03', 'c')]}
    _check_no_gaps(result)  # raise 없어야 함


def test_check_no_gaps_raises_on_missing_number():
    result = {'함수의 극한': [('01', 'a'), ('03', 'c')]}  # 02가 없음
    with pytest.raises(ValueError, match='구멍'):
        _check_no_gaps(result)


def test_apply_known_ocr_fixes_corrects_number_by_title_lookup():
    # 실제 겪은 사례 재현: '17'의 '7'이 OCR에서 사라져 '1'로만 잡힘
    result = {
        '도함수의 활용 ⑶': [
            ('01', '시각에 대한 길이의 변화율'),  # 원래는 17이어야 함
            ('18', '시각에 대한 넓이의 변화율'),
        ]
    }
    _apply_known_ocr_fixes(result)
    nums = dict(result['도함수의 활용 ⑶'])
    assert '17' in nums
    assert nums['17'] == '시각에 대한 길이의 변화율'


def test_apply_known_ocr_fixes_noop_when_already_correct():
    result = {'도함수의 활용 ⑶': [('17', '시각에 대한 길이의 변화율')]}
    _apply_known_ocr_fixes(result)
    assert result['도함수의 활용 ⑶'] == [('17', '시각에 대한 길이의 변화율')]
