import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Base, Chapter, Problem
from pdf_rpm_extract import RpmSubsectionGroup
from import_rpm_problems import insert_subsections


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


def test_insert_creates_one_row_per_subsection(session, chapter):
    group = RpmSubsectionGroup(
        section_name="수열의 극한", subsection_name="수열의 극한",
        image_paths=["img/0006.png", "img/0007.png"],
        text_parts=["문제 내용"],
    )
    created = insert_subsections(session, [group], pdf_path="x.pdf")

    assert created == 1
    row = session.query(Problem).one()
    assert row.problem_type.subsection.name == "수열의 극한"
    assert json.loads(row.image_paths) == ["img/0006.png", "img/0007.png"]


def test_insert_is_idempotent(session, chapter):
    group = RpmSubsectionGroup(
        section_name="수열의 극한", subsection_name="수열의 극한",
        image_paths=["img/0006.png"], text_parts=["stem"],
    )
    insert_subsections(session, [group], pdf_path="x.pdf")
    created = insert_subsections(session, [group], pdf_path="x.pdf")

    assert created == 0
    assert session.query(Problem).count() == 1
