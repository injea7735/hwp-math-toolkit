import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sumaessing_answer_extract import _NUMBER_ANSWER_LINE


def test_matches_number_and_answer_on_same_line():
    m = _NUMBER_ANSWER_LINE.match('0121  ③')
    assert m.group(1) == '0121'
    assert m.group(2) == '③'


def test_matches_multi_part_answer():
    m = _NUMBER_ANSWER_LINE.match('0002  ⑴ 수렴, 0  ⑵ 발산')
    assert m.group(1) == '0002'
    assert m.group(2) == '⑴ 수렴, 0  ⑵ 발산'


def test_rejects_plain_prose_line():
    assert _NUMBER_ANSWER_LINE.match('따라서 옳은 것은 ㄴ뿐이다.') is None
