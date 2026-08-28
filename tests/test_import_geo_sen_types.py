import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, ProblemType
from import_geo_sen_types import insert_types


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


SUBSECTION_ORDER = [('이차곡선', '이차곡선')]
TOC = {'이차곡선': [('01', '포물선의 방정식'), ('02', '포물선의 평행이동')]}


def test_insert_types_creates_chapter_and_real_named_types(session):
    # 기하는 미적분1과 달리 이전에 아무 데이터도 없던 새 Chapter라 stale
    # 정리가 필요 없다 - insert_types가 Chapter까지 알아서 만들어야 한다.
    created = insert_types(session, SUBSECTION_ORDER, TOC)

    assert created == 2
    chapter = session.query(Chapter).filter_by(name='기하').one()
    types = session.query(ProblemType).order_by(ProblemType.order).all()
    assert [t.name for t in types] == ['포물선의 방정식', '포물선의 평행이동']
    assert types[0].code == '기하-쎈-이차곡선-유형01'
    assert types[0].subsection.section.chapter_id == chapter.id


def test_insert_types_idempotent(session):
    insert_types(session, SUBSECTION_ORDER, TOC)
    created_again = insert_types(session, SUBSECTION_ORDER, TOC)

    assert created_again == 0
    assert session.query(ProblemType).count() == 2
