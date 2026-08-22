"""
2022개정 교육과정 대단원>소단원 구조를 taxonomy(Chapter/Section/SubSection)에 심는다.

일부 교재(대수/미적분Ⅰ/확률과 통계/미적분Ⅱ의 "내신고쟁이"/"쎈수학" PDF 유형서)는
문제를 이름 붙은 유형이 아니라 난이도 단계(DifficultyTier)로만 묶어서 제공하고,
페이지 레이아웃도 단원 구조를 안정적으로 자동 추출하기 어렵다. 반면 대단원/소단원
체계 자체는 교육과정에 공식적으로 정해져 있으므로, 이 파일에서는 PDF를 파싱하는
대신 교육과정 표준 명칭을 직접 넣는다. ProblemType(유형)은 아직 만들지 않는다 —
유형 데이터가 없는 과목이므로 비워 둔다.

"대수" 단원명은 실제 PDF 대단원 도입부 페이지 텍스트로 확인했다.
"미적분1"/"확률과 통계"는 대단원명 일부만 PDF로 확인, 소단원명은 교육과정 표준 명칭.
"미적분2"(쎈수학 PDF)는 원본이 텍스트 레이어 없는 스캔본이라 대조하지 못했다 — 미검증.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from import_workbook_outline import (
    get_or_create_chapter, get_or_create_section, get_or_create_subsection,
)
from models import init_db

CURRICULUM: dict[str, list[tuple[str, list[str]]]] = {
    '대수': [
        ('지수함수와 로그함수', ['지수와 로그', '지수함수와 로그함수']),
        ('삼각함수', ['삼각함수', '사인법칙과 코사인법칙']),
        ('수열', ['등차수열과 등비수열', '수열의 합', '수학적 귀납법']),
    ],
    '미적분1': [
        ('함수의 극한과 연속', ['함수의 극한', '함수의 연속']),
        ('미분', ['미분계수와 도함수', '도함수의 활용']),
        ('적분', ['부정적분과 정적분', '정적분의 활용']),
    ],
    '확률과 통계': [
        ('경우의 수', ['여러 가지 순열', '중복조합과 이항정리']),
        ('확률', ['확률의 뜻과 활용', '조건부확률']),
        ('통계', ['확률변수와 확률분포', '통계적 추정']),
    ],
    '미적분2': [  # 미검증 (원본이 스캔 PDF라 대조 못 함)
        ('수열의 극한', ['수열의 극한', '급수']),
        ('미분법', ['여러 가지 함수의 미분', '여러 가지 미분법', '도함수의 활용']),
        ('적분법', ['여러 가지 적분법', '정적분의 활용']),
    ],
}


def seed(session: Session) -> None:
    for subject, sections in CURRICULUM.items():
        chapter = get_or_create_chapter(session, subject)
        for section_name, subsection_names in sections:
            section = get_or_create_section(session, chapter, section_name)
            for sub_name in subsection_names:
                get_or_create_subsection(session, section, sub_name)


if __name__ == '__main__':
    engine = init_db()
    with Session(engine) as session:
        seed(session)
        session.commit()
    print('완료')
