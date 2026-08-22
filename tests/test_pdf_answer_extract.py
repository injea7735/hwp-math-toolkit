import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_answer_extract import _strip_leading_noise, _NUMBER_LINE


def test_number_line_matches_plain_number():
    assert _NUMBER_LINE.match('001')


def test_number_line_tolerates_trailing_control_char():
    # 실제 자료에서 확인됨: 번호 뒤에 공백 + 백스페이스(\x08) 제어문자가
    # 붙어 나온다(폰트 커닝 힌트로 추정).
    assert _NUMBER_LINE.match('001   \x08')


def test_number_line_rejects_non_number_lines():
    assert not _NUMBER_LINE.match('8의 세제곱근을 모두 구하시오.')
    assert not _NUMBER_LINE.match('0012')  # 4자리는 문제번호가 아니다


def test_strip_leading_noise_removes_pua_icon_and_spaces():
    # 실제 자료: 정답 줄 맨 앞에 "정답" 라벨 아이콘(PUA 코드포인트, U+E3BD)이
    # 공백과 함께 붙어 나온다.
    icon = chr(0xE3BD)
    assert _strip_leading_noise(f'  {icon} 2, -1{chr(0xD1)}\'3i') == "2, -1Ñ'3i"


def test_strip_leading_noise_leaves_plain_text_untouched():
    assert _strip_leading_noise('③') == '③'
