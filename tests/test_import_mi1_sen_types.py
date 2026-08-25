import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, ProblemType
from import_mi1_sen_types import delete_stale_sen_types, insert_types


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def chapter(session):
    ch = Chapter(name="미적분1")
    session.add(ch)
    session.commit()
    return ch


SUBSECTION_ORDER = [('함수의 극한과 연속', '함수의 극한')]
TOC = {'함수의 극한': [('01', '함수의 극한값의 존재'), ('02', '함수의 극한값 구하기')]}


def test_insert_types_creates_real_named_types(session, chapter):
    created = insert_types(session, SUBSECTION_ORDER, TOC)

    assert created == 2
    types = session.query(ProblemType).order_by(ProblemType.order).all()
    assert [t.name for t in types] == ['함수의 극한값의 존재', '함수의 극한값 구하기']
    assert types[0].code == '미적분1-쎈-함수의 극한-유형01'


def test_insert_types_idempotent(session, chapter):
    insert_types(session, SUBSECTION_ORDER, TOC)
    created_again = insert_types(session, SUBSECTION_ORDER, TOC)

    assert created_again == 0
    assert session.query(ProblemType).count() == 2


def test_delete_stale_sen_types_only_removes_sen_prefixed_ones(session, chapter):
    from import_workbook_outline import get_or_create_section, get_or_create_subsection
    section = get_or_create_section(session, chapter, '함수의 극한과 연속')
    subsection = get_or_create_subsection(session, section, '함수의 극한')
    stale = ProblemType(
        subsection_id=subsection.id, code='미적분1-쎈-함수의 극한-유형01',
        name='구교육과정 대체', order=1,
    )
    unrelated = ProblemType(
        subsection_id=subsection.id, code='미적분1-함수의 극한과 연속-미분류',
        name='난이도만 구분', order=0,
    )
    session.add_all([stale, unrelated])
    session.commit()

    deleted = delete_stale_sen_types(session)

    assert deleted == 1
    remaining = session.query(ProblemType).all()
    assert len(remaining) == 1
    assert remaining[0].code == '미적분1-함수의 극한과 연속-미분류'
