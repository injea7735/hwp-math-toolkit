import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hwp_sen_daepyo_parse import _parse_texts


def test_extracts_type_title_and_representative_problem_no():
    texts = [
        '[', '유형 ', '01', ']', '수열의 수렴과 발산',
        '0044', '문제 지문 ①', '② ③',
        '[', '유형 ', '02', ']', '수열의 극한에 대한 기본 성질',
        '0047', '문제 지문',
    ]
    entries = _parse_texts(texts)

    assert [(e.type_no, e.title, e.problem_no) for e in entries] == [
        ('01', '수열의 수렴과 발산', '0044'),
        ('02', '수열의 극한에 대한 기본 성질', '0047'),
    ]


def test_type_no_and_closing_bracket_glued_together():
    # 보통 'NN'과 ']'가 따로 나오지만, 가끔 'NN]'처럼 한 조각으로 붙어 나온다.
    texts = [
        '[', '유형 ', '12]', '사잇값의 정리의 실생활에의 활용',
        '0203', '문제 지문',
    ]
    entries = _parse_texts(texts)

    assert (entries[0].type_no, entries[0].title, entries[0].problem_no) == (
        '12', '사잇값의 정리의 실생활에의 활용', '0203',
    )


def test_type_word_and_number_glued_together():
    # '유형'과 번호가 '유형 20'처럼 한 조각으로 붙고, ']'는 따로 나오는 경우.
    texts = [
        '[', '유형 20', ']', ' ', '삼각부등식; 이차식의 꼴',
        '0757', '문제 지문',
    ]
    entries = _parse_texts(texts)

    assert (entries[0].type_no, entries[0].title, entries[0].problem_no) == (
        '20', '삼각부등식; 이차식의 꼴', '0757',
    )


def test_answer_taken_from_second_occurrence_not_body_text():
    # 0044 재등장 직후 '③'이 정답. 0044 첫 등장 뒤에 곧바로 나오는 본문
    # 텍스트('①의 경우...')를 정답으로 착각하면 안 된다.
    texts = [
        '[', '유형 ', '01', ']', '제목',
        '0044', '①의 경우 성립.',
        '01', '수열의 극한',
        '0044', '③',
    ]
    entries = _parse_texts(texts)

    assert entries[0].answer == '③'


def test_answer_none_when_problem_no_appears_only_once():
    # 정답표에 다시 나오지 않으면(자료 누락) 정답을 None으로 둔다.
    texts = ['[', '유형 ', '01', ']', '제목', '0044', '문제 지문']
    entries = _parse_texts(texts)

    assert entries[0].answer is None


def test_answer_none_when_answer_table_cell_is_blank():
    # 서술형 문제는 정답표에서 바로 다음 번호로 넘어간다(빈 칸).
    texts = [
        '[', '유형 ', '01', ']', '제목1', '0044', '지문',
        '[', '유형 ', '02', ']', '제목2', '0047', '지문',
        '01', '수열의 극한',
        '0044', '0047', '⑤',
    ]
    entries = _parse_texts(texts)

    by_no = {e.problem_no: e for e in entries}
    assert by_no['0044'].answer is None
    assert by_no['0047'].answer == '⑤'


def test_answer_none_when_next_fragment_has_no_circled_symbol():
    # 합답형 문제 중 일부는 원문자 글자가 텍스트로 추출되지 않고
    # ' 또는 '/', ' 같은 연결어 조각만 남는다 - 이건 정답이 아니라
    # 자료 누락이므로 None으로 둬야 한다.
    texts = [
        '[', '유형 ', '01', ']', '제목', '0044', '지문',
        '01', '수열의 극한',
        '0044', ' 또는 ',
    ]
    entries = _parse_texts(texts)

    assert entries[0].answer is None


def test_answer_can_be_a_latex_equation_fragment():
    # EqEdit로 적힌 서술형 정답은 '$...$'로 이미 감싸져 들어온다.
    texts = [
        '[', '유형 ', '01', ']', '제목', '0044', '지문',
        '01', '수열의 극한',
        '0044', '$6$',
    ]
    entries = _parse_texts(texts)

    assert entries[0].answer == '$6$'
