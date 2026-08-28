import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backfill_sen_difficulty import backfill
from models import Base, Chapter, Problem, ProblemType, Section, SubSection


@pytest.fixture
def session(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        chapter = Chapter(name="기하")
        s.add(chapter)
        s.flush()
        section = Section(name="이차곡선", chapter_id=chapter.id)
        s.add(section)
        s.flush()
        subsection = SubSection(name="포물선", section_id=section.id)
        s.add(subsection)
        s.flush()
        ptype = ProblemType(name="유형01", code="G-01-01-01", subsection_id=subsection.id)
        s.add(ptype)
        s.flush()

        # 흰 배경(배지 없음)짜리 진짜 이미지가 필요하므로 임시 png를 만든다.
        from PIL import Image

        blank_path = tmp_path / "not_sen.png"
        Image.new("RGB", (400, 45), (255, 255, 255)).save(blank_path)

        # detect_badges가 신호를 못 찾는 흰 이미지를 두 출처에 걸쳐 넣는다:
        # 하나는 파일명에 "쎈수학"이 들어있고(대상), 하나는 안 들어있다(제외 대상).
        sen_path = tmp_path / "쎈수학_문제.png"
        Image.new("RGB", (400, 45), (255, 255, 255)).save(sen_path)

        p_sen = Problem(
            problem_type_id=ptype.id,
            stem_latex="(이미지 참고)",
            question_kind="객관식",
            image_paths=json.dumps([str(sen_path)], ensure_ascii=False),
        )
        p_other = Problem(
            problem_type_id=ptype.id,
            stem_latex="원래 텍스트 문제",
            question_kind="단답형",
            difficulty_label=None,
            image_paths=json.dumps([str(blank_path)], ensure_ascii=False),
        )
        s.add_all([p_sen, p_other])
        s.commit()
        yield s, p_sen.id, p_other.id


def test_backfill_only_touches_sen_origin_rows(session):
    s, sen_id, other_id = session
    result = backfill(s, "기하", apply=True)
    assert result["total"] == 1  # 쎈수학 이미지 1건만 대상

    other = s.get(Problem, other_id)
    # 쎈수학이 아닌 출처는 절대 건드리면 안 된다 - 원래 question_kind 그대로.
    assert other.question_kind == "단답형"
    assert other.difficulty_label is None
