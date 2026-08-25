import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_mi1_sen_extract import (
    _is_daepyo_pill_mi1, _is_type_pill_mi1, _norm_title, _title_similarity,
)


def test_type_pill_size_and_color():
    # 실측 정상 케이스 (63x35, 청록빛 초록)
    assert _is_type_pill_mi1((91, 128, 63, 35, (48, 168, 164))) is True


def test_type_pill_rejects_concept_reference_badge():
    # "개념 NN-N" 참조 배지 - 진짜 유형 알약과 크기가 겹치던 실측값
    assert _is_type_pill_mi1((241, 139, 56, 26, (167, 192, 74))) is False


def test_type_pill_rejects_low_saturation_green():
    x, y, w, h = 91, 128, 63, 35
    assert _is_type_pill_mi1((x, y, w, h, (100, 105, 100))) is False


def test_daepyo_pill_accepts_orange_shifted_color():
    # 실측: r-g=42인데도 진짜 대표문제 알약(육안 대조 확인함)
    assert _is_daepyo_pill_mi1((102, 658, 137, 30, (239, 197, 70))) is True


def test_daepyo_pill_rejects_gold_badge_same_size():
    # 크기만 겹치는 금색 배지 (r-g=3, 진짜 빨강이 아님)
    assert _is_daepyo_pill_mi1((223, 1238, 134, 23, (230, 227, 97))) is False


def test_title_similarity_identical():
    assert _title_similarity('함수의 극한값의 존재', '함수의 극한값의 존재') == 1.0


def test_title_similarity_ocr_noise_still_matches():
    real = '. 함수의 극한값의 존재            소 기니0'
    assert _title_similarity('함수의 극한값의 존재', real) >= 0.9


def test_title_similarity_different_topics_score_low():
    a = '함수의 극한값의 존재'
    b = '접선의 기울기'
    assert _title_similarity(a, b) < 0.5


def test_title_similarity_shared_prefix_scores_higher():
    # 알려진 한계: 같은 소단원 안의 유형들은 "부정적분과..." 같은 공통
    # 어절을 접두로 공유해서, 글자 집합만 보는 이 함수는 서로 다른
    # 유형끼리도 어느 정도 유사도가 나온다 - 그래도 임계값(0.5) 근처에
    # 걸치는 수준이라 실제 재동기화에서는 "더 잘 맞는 후보"를 고르는
    # 방식으로 충분히 구분됐다(운영 데이터로 확인함).
    a = '부정적분과 극대ㆍ극소'
    b = '부정적분과 도함수의 정의를 이용하여 함수 구하기'
    assert _title_similarity(a, b) > 0.5


def test_title_similarity_empty_is_zero():
    assert _title_similarity('아무 제목', '') == 0.0
    assert _title_similarity('', '아무 제목') == 0.0


def test_norm_title_strips_non_korean_non_digit():
    assert _norm_title('. 함수의 연속(2)  개") ') == '함수의연속2개'
