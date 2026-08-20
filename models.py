"""
문제은행 DB 스키마 초안 (SQLAlchemy ORM)

설계 원칙
---------
- taxonomy(대단원/중단원/소단원/유형)는 코드가 아니라 DB 데이터로 관리한다.
  -> 구조 변경(유형 추가/이름변경/이동)은 코드 수정 없이 데이터 편집만으로 즉시 반영됨.
- 문제 하나는 "유형(ProblemType)" 하나에 소속되면서, 필요한 "개념(Concept)"들을 태그로 여러 개 매핑한다.
  (대화에서 확정한 마플교과서식 개념+유형 통합 구조)
- 난이도는 숫자 점수 + 정성 라벨의 이중 구조, 그리고 별도 축으로 A/B/C 학습단계(step)를 둔다.
- 배점(score) 필드는 넣지 않는다 — 학교별로 배치가 달라 참고용일 뿐 필요성이 낮다는 결정을 반영.
- SQLite로 시작하되, SQLAlchemy로 감싸두어 나중에 PostgreSQL로 옮길 때 코드 변경이 거의 없게 한다.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    create_engine, ForeignKey, String, Text, Integer, Float, DateTime,
    Boolean, Table, Column, UniqueConstraint
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# taxonomy: 대단원 > 중단원 > 소단원 > 유형(ProblemType)
# ---------------------------------------------------------------------------

class Chapter(Base):
    """대단원 (예: 미적분Ⅰ, 확률과 통계, 공통수학2 ...)"""
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    order: Mapped[int] = mapped_column(Integer, default=0)  # 표시 순서

    sections: Mapped[list["Section"]] = relationship(back_populates="chapter")


class Section(Base):
    """중단원 (예: 지수함수와 로그함수, 조건부확률 ...)"""
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"))
    name: Mapped[str] = mapped_column(String(100))
    order: Mapped[int] = mapped_column(Integer, default=0)

    chapter: Mapped["Chapter"] = relationship(back_populates="sections")
    subsections: Mapped[list["SubSection"]] = relationship(back_populates="section")

    __table_args__ = (UniqueConstraint("chapter_id", "name", name="uq_section_per_chapter"),)


class SubSection(Base):
    """소단원 (예: 지수함수의 그래프, 로그함수의 성질 ...)"""
    __tablename__ = "subsections"

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    name: Mapped[str] = mapped_column(String(100))
    order: Mapped[int] = mapped_column(Integer, default=0)

    section: Mapped["Section"] = relationship(back_populates="subsections")
    problem_types: Mapped[list["ProblemType"]] = relationship(back_populates="subsection")

    __table_args__ = (UniqueConstraint("section_id", "name", name="uq_subsection_per_section"),)


class ProblemType(Base):
    """유형 (예: T-201 지수함수 그래프 개형, T-202 지수함수 평행이동 ...)
    문제는 이 유형에 정확히 하나 소속된다."""
    __tablename__ = "problem_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    subsection_id: Mapped[int] = mapped_column(ForeignKey("subsections.id"))
    code: Mapped[str] = mapped_column(String(20), unique=True)   # 예: "T-201"
    name: Mapped[str] = mapped_column(String(200))                # 예: "지수함수 그래프 개형 판별"
    order: Mapped[int] = mapped_column(Integer, default=0)

    subsection: Mapped["SubSection"] = relationship(back_populates="problem_types")
    problems: Mapped[list["Problem"]] = relationship(back_populates="problem_type")


class Concept(Base):
    """개념 태그 (예: 지수법칙, 로그의 성질, 절댓값 부등식 ...)
    문제 하나에 여러 개 매핑 가능 (다대다)."""
    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


problem_concepts = Table(
    "problem_concepts",
    Base.metadata,
    Column("problem_id", ForeignKey("problems.id"), primary_key=True),
    Column("concept_id", ForeignKey("concepts.id"), primary_key=True),
)


# ---------------------------------------------------------------------------
# 문제 본체
# ---------------------------------------------------------------------------

class Source(Base):
    """출처 (학교명·시험명·연도 등)"""
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    school: Mapped[str | None] = mapped_column(String(100), nullable=True)
    exam_name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 예: "2025 중간고사"
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    material_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # 자료 성격 구분: "기출"(exam) / "N제"(practice) / "개념정리"(theory) 등
    # -> 배점 유무처럼 자료 성격에 따라 달라지는 필드를 다룰 때 이 값으로 분기

    problems: Mapped[list["Problem"]] = relationship(back_populates="source")


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(primary_key=True)

    problem_type_id: Mapped[int] = mapped_column(ForeignKey("problem_types.id"))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)

    stem_latex: Mapped[str] = mapped_column(Text)          # 문제 지문 (LaTeX 수식 포함)
    choices_latex: Mapped[str | None] = mapped_column(Text, nullable=True)  # 객관식 보기 (JSON 문자열 또는 구분자로 저장)
    answer: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 원문자 또는 단답형 값(LaTeX)
    question_kind: Mapped[str] = mapped_column(String(20), default="객관식")  # 객관식 / 서술형 / 단답형

    # 난이도: 숫자 점수 + 정성 라벨 이중 구조 (수학비서식)
    difficulty_score: Mapped[float | None] = mapped_column(Float, nullable=True)   # 예: 4, 5, 6
    difficulty_label: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 쉬움/보통/어려움/매우어려움

    # A/B/C 학습 단계 축 (난이도와 별도)
    learning_step: Mapped[str | None] = mapped_column(String(1), nullable=True)  # 'A' / 'B' / 'C'

    original_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 네이버 BOX 동기화 폴더 기준 상대경로 등 원본 파일 위치 추적용

    image_paths: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 배열 문자열 (문제 삽화 파일 경로들)

    ngd_problem_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    # NGD 문제은행(exam.db)에서 가져온 문제의 원본 problems.id. 재수입 시 중복 방지용 키.

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    problem_type: Mapped["ProblemType"] = relationship(back_populates="problems")
    source: Mapped["Source | None"] = relationship(back_populates="problems")
    concepts: Mapped[list["Concept"]] = relationship(secondary=problem_concepts)
    attempts: Mapped[list["Attempt"]] = relationship(back_populates="problem")


# ---------------------------------------------------------------------------
# 학습데이터: 학생이 어떤 문제를 언제 풀어서 맞았는지/틀렸는지 기록
# -> 유형별 정답률을 계산해 취약 유형을 뽑아내는 데 쓰인다 (recommend.py)
# ---------------------------------------------------------------------------

class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))

    attempts: Mapped[list["Attempt"]] = relationship(back_populates="student")


class Attempt(Base):
    """학생의 문제 풀이 시도 1건."""
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    student: Mapped["Student"] = relationship(back_populates="attempts")
    problem: Mapped["Problem"] = relationship(back_populates="attempts")


# ---------------------------------------------------------------------------
# 초기화 헬퍼
# ---------------------------------------------------------------------------

def init_db(db_path: str = "sqlite:///math_bank.db"):
    engine = create_engine(db_path, echo=False)
    Base.metadata.create_all(engine)
    return engine


if __name__ == "__main__":
    engine = init_db()
    print("DB 초기화 완료:", engine.url)
