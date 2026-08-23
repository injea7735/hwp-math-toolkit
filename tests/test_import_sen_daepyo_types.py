import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, ProblemType, Section, SubSection
from hwp_sen_daepyo_parse import RepresentativeType
from import_sen_daepyo_types import insert_types, _match_subsection, FILE_TO_SUBSECTION_BY_SUBJECT


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def chapter(session):
    ch = Chapter(name="미적분2")
    session.add(ch)
    session.commit()
    return ch


def test_matches_filename_to_canonical_subsection():
    m = FILE_TO_SUBSECTION_BY_SUBJECT['미적분2']
    assert _match_subsection('쎈_08 여러 가지 함수의 적분법.hwp', m) == ('적분법', '여러 가지 적분법')
    assert _match_subsection('쎈_09 치환적분법과 부분적분법.hwp', m) == ('적분법', '정적분')
    assert _match_subsection('쎈_01 수열의 극한.hwp', m) == ('수열의 극한', '수열의 극한')


def test_matches_algebra_and_probstat_filenames():
    algebra = FILE_TO_SUBSECTION_BY_SUBJECT['대수']
    assert _match_subsection('쎈_01 지수.hwp', algebra) == ('지수함수와 로그함수', '지수')
    assert _match_subsection('쎈_06 삼각함수의 그래프.hwp', algebra) == ('삼각함수', '삼각함수의 그래프')

    probstat = FILE_TO_SUBSECTION_BY_SUBJECT['확률과 통계']
    assert _match_subsection('쎈_06 이항분포와 정규분포.hwp', probstat) == ('통계', '이항분포와 정규분포')


def test_unmatched_filename_raises(session, chapter):
    with pytest.raises(ValueError):
        insert_types(session, '미적분2', '알 수 없는 파일.hwp', [])


def test_creates_problem_type_with_real_title_and_order(session, chapter):
    entries = [
        RepresentativeType(type_no='01', title='수열의 수렴과 발산', problem_no='0044', answer='③'),
        RepresentativeType(type_no='02', title='수열의 극한에 대한 기본 성질', problem_no='0047'),
    ]
    created = insert_types(session, '미적분2', '쎈_01 수열의 극한.hwp', entries)

    assert created == 2
    section = session.query(Section).filter_by(chapter_id=chapter.id, name='수열의 극한').one()
    subsection = session.query(SubSection).filter_by(section_id=section.id, name='수열의 극한').one()
    types = session.query(ProblemType).filter_by(subsection_id=subsection.id).all()
    names_by_order = {t.order: t.name for t in types}
    assert names_by_order == {1: '수열의 수렴과 발산', 2: '수열의 극한에 대한 기본 성질'}


def test_reuses_existing_subsection_from_another_source(session, chapter):
    # RPM/수매씽이 이미 만들어 둔 정식 소단원("적분법"/"정적분")에
    # 쎈수학 유형이 합쳐져야지, 새 소단원을 또 만들면 안 된다.
    from import_workbook_outline import get_or_create_section, get_or_create_subsection
    section = get_or_create_section(session, chapter, '적분법')
    get_or_create_subsection(session, section, '정적분')

    entries = [RepresentativeType(type_no='01', title='치환적분법; 유리함수', problem_no='1062', answer='②')]
    insert_types(session, '미적분2', '쎈_09 치환적분법과 부분적분법.hwp', entries)

    subsections = session.query(SubSection).filter_by(section_id=section.id).all()
    assert len(subsections) == 1


def test_idempotent_rerun_creates_no_duplicates(session, chapter):
    entries = [RepresentativeType(type_no='01', title='수열의 수렴과 발산', problem_no='0044', answer='③')]
    insert_types(session, '미적분2', '쎈_01 수열의 극한.hwp', entries)
    created_again = insert_types(session, '미적분2', '쎈_01 수열의 극한.hwp', entries)

    assert created_again == 0
