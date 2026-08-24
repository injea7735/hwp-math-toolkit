import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, Problem, ProblemType
from pdf_sen_extract import SenProblem
from import_sen_problems import insert_problems


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


def _sen_problem(**overrides):
    defaults = dict(
        section_name='수열의 극한', subsection_name='수열의 극한',
        type_no='01', type_title='수열의 수렴과 발산',
        number='0044', is_daepyo=True, answer='③',
        page_index=17, image_path='img/0044.png',
    )
    defaults.update(overrides)
    return SenProblem(**defaults)


def test_reuses_existing_problem_type_from_taxonomy_seeding(session, chapter):
    from import_workbook_outline import get_or_create_section, get_or_create_subsection
    section = get_or_create_section(session, chapter, '수열의 극한')
    subsection = get_or_create_subsection(session, section, '수열의 극한')
    existing = ProblemType(
        subsection_id=subsection.id, code='미적분2-쎈-수열의 극한-유형01',
        name='수열의 수렴과 발산', order=1,
    )
    session.add(existing)
    session.commit()

    created = insert_problems(session, '미적분2', [_sen_problem()], pdf_path='x.pdf')

    assert created == 1
    types = session.query(ProblemType).filter_by(subsection_id=subsection.id).all()
    assert len(types) == 1  # 새로 안 만들고 기존 걸 재사용


def test_daepyo_problem_gets_answer_from_hwp(session, chapter):
    insert_problems(session, '미적분2', [_sen_problem(answer='③')], pdf_path='x.pdf')

    problem = session.query(Problem).one()
    assert problem.answer == '③'


def test_regular_problem_has_no_answer(session, chapter):
    p = _sen_problem(number='0045', is_daepyo=False, answer=None, image_path='img/0045.png')
    insert_problems(session, '미적분2', [p], pdf_path='x.pdf')

    problem = session.query(Problem).one()
    assert problem.answer is None


def test_idempotent_rerun_by_image_path(session, chapter):
    p = _sen_problem()
    insert_problems(session, '미적분2', [p], pdf_path='x.pdf')
    created_again = insert_problems(session, '미적분2', [p], pdf_path='x.pdf')

    assert created_again == 0
    assert session.query(Problem).count() == 1


def test_fallback_named_image_flagged_for_review(session, chapter):
    # 번호 OCR 실패로 'col{열}-{순번}' 식 임시 이름이 붙은 경우 - 파일이
    # 실제로 존재하지 않아도(테스트용 가짜 경로) 이름 패턴만으로 걸린다.
    p = _sen_problem(number=None, image_path='img/0060_col1-2.png')
    insert_problems(session, '미적분2', [p], pdf_path='x.pdf')

    problem = session.query(Problem).one()
    assert problem.needs_review is True


def test_tall_crop_flagged_for_review(session, chapter, tmp_path):
    from PIL import Image
    img_path = tmp_path / '0055.png'
    Image.new('RGB', (800, 1800), 'white').save(img_path)
    p = _sen_problem(image_path=str(img_path))

    insert_problems(session, '미적분2', [p], pdf_path='x.pdf')

    problem = session.query(Problem).one()
    assert problem.needs_review is True


def test_normal_crop_not_flagged(session, chapter, tmp_path):
    from PIL import Image
    img_path = tmp_path / '0056.png'
    Image.new('RGB', (800, 600), 'white').save(img_path)
    p = _sen_problem(image_path=str(img_path))

    insert_problems(session, '미적분2', [p], pdf_path='x.pdf')

    problem = session.query(Problem).one()
    assert problem.needs_review is False
    assert problem.source_page_index == 17
