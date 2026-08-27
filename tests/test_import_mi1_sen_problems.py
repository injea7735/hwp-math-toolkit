import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, Problem, ProblemType
from import_workbook_outline import get_or_create_section, get_or_create_subsection
from pdf_mi1_sen_extract import Mi1Problem
from import_mi1_sen_problems import insert_problems


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def problem_type(session):
    ch = Chapter(name="미적분1")
    session.add(ch)
    session.flush()
    section = get_or_create_section(session, ch, '함수의 극한과 연속')
    subsection = get_or_create_subsection(session, section, '함수의 극한')
    pt = ProblemType(
        subsection_id=subsection.id, code='미적분1-쎈-함수의 극한-유형01',
        name='함수의 극한값의 존재', order=1,
    )
    session.add(pt)
    session.commit()
    return pt


def _mi1_problem(**overrides):
    defaults = dict(
        section_name='함수의 극한과 연속', subsection_name='함수의 극한',
        type_no='01', type_title='함수의 극한값의 존재',
        number='0044', is_daepyo=True,
        page_index=11, image_path='img/0044.png',
    )
    defaults.update(overrides)
    return Mi1Problem(**defaults)


def test_reuses_type_seeded_by_import_mi1_sen_types(session, problem_type):
    created = insert_problems(session, [_mi1_problem()], pdf_path='x.pdf')

    assert created == 1
    assert session.query(ProblemType).count() == 1  # 새로 안 만듦
    problem = session.query(Problem).one()
    assert problem.problem_type_id == problem_type.id
    assert problem.answer is None  # 미적분1은 대표문제 정답 소스가 없음


def test_raises_when_type_not_seeded(session):
    ch = Chapter(name="미적분1")
    session.add(ch)
    session.commit()

    with pytest.raises(ValueError, match='ProblemType 없음'):
        insert_problems(session, [_mi1_problem()], pdf_path='x.pdf')


def test_idempotent_rerun_by_image_path(session, problem_type):
    p = _mi1_problem()
    insert_problems(session, [p], pdf_path='x.pdf')
    created_again = insert_problems(session, [p], pdf_path='x.pdf')

    assert created_again == 0
    assert session.query(Problem).count() == 1


def test_fallback_named_image_flagged_for_review(session, problem_type):
    p = _mi1_problem(number=None, image_path='img/0044_col1-2.png')
    insert_problems(session, [p], pdf_path='x.pdf')

    assert session.query(Problem).one().needs_review is True


def test_tall_crop_flagged_for_review(session, problem_type, tmp_path):
    from PIL import Image
    img_path = tmp_path / '0044.png'
    Image.new('RGB', (800, 1800), 'white').save(img_path)

    insert_problems(session, [_mi1_problem(image_path=str(img_path))], pdf_path='x.pdf')

    assert session.query(Problem).one().needs_review is True
