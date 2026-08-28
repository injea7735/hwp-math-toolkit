import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, Problem, ProblemType
from import_workbook_outline import get_or_create_section, get_or_create_subsection
from pdf_mi1_sen_extract import Mi1Problem
from import_geo_sen_problems import insert_problems


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def problem_type(session):
    ch = Chapter(name="기하")
    session.add(ch)
    session.flush()
    section = get_or_create_section(session, ch, '이차곡선')
    subsection = get_or_create_subsection(session, section, '이차곡선')
    pt = ProblemType(
        subsection_id=subsection.id, code='기하-쎈-이차곡선-유형01',
        name='포물선의 방정식', order=1,
    )
    session.add(pt)
    session.commit()
    return pt


def _geo_problem(**overrides):
    defaults = dict(
        section_name='이차곡선', subsection_name='이차곡선',
        type_no='01', type_title='포물선의 방정식',
        number='0041', is_daepyo=True,
        page_index=17, image_path='img/0041.png',
    )
    defaults.update(overrides)
    return Mi1Problem(**defaults)


def test_reuses_type_seeded_by_import_geo_sen_types(session, problem_type):
    created = insert_problems(session, [_geo_problem()], pdf_path='x.pdf')

    assert created == 1
    assert session.query(ProblemType).count() == 1  # 새로 안 만듦
    problem = session.query(Problem).one()
    assert problem.problem_type_id == problem_type.id
    assert problem.answer is None  # 기하도 대표문제 정답 소스가 없음


def test_raises_when_type_not_seeded(session):
    ch = Chapter(name="기하")
    session.add(ch)
    session.commit()

    with pytest.raises(ValueError, match='ProblemType 없음'):
        insert_problems(session, [_geo_problem()], pdf_path='x.pdf')


def test_idempotent_rerun_by_image_path(session, problem_type):
    p = _geo_problem()
    insert_problems(session, [p], pdf_path='x.pdf')
    created_again = insert_problems(session, [p], pdf_path='x.pdf')

    assert created_again == 0
    assert session.query(Problem).count() == 1


def test_fallback_named_image_flagged_for_review(session, problem_type):
    p = _geo_problem(number=None, image_path='img/0041_col1-2.png')
    insert_problems(session, [p], pdf_path='x.pdf')

    assert session.query(Problem).one().needs_review is True


def test_tall_crop_flagged_for_review(session, problem_type, tmp_path):
    from PIL import Image
    img_path = tmp_path / '0041.png'
    Image.new('RGB', (800, 1800), 'white').save(img_path)

    insert_problems(session, [_geo_problem(image_path=str(img_path))], pdf_path='x.pdf')

    assert session.query(Problem).one().needs_review is True
