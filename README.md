# hwp-math-toolkit

수학 문제은행 구축을 위한 작은 도구 모음.

## 구성

- **`hwp_eq_to_latex.py`** — 한글(HWP) 수식 편집기 스크립트(DSL)를 LaTeX로 변환하는 파서.
  `^`, `_`, `over`, `sqrt`, `bar`, `rm`, `LEFT`/`RIGHT` 등 자주 쓰이는 수식 표현을 지원한다.
- **`models.py`** — 문제은행 DB 스키마 초안(SQLAlchemy ORM). 대단원/중단원/소단원/유형(taxonomy)과
  개념(Concept) 태그, 문제(Problem), 출처(Source)를 다룬다.

## 설치

```bash
pip install -r requirements.txt
```

## 사용 예시

```python
from hwp_eq_to_latex import hwp_eq_to_latex

hwp_eq_to_latex("t ^{2} le{17} over {2}")
# -> 't^{2} \\le \\frac{17}{2}'
```

```python
from models import init_db

engine = init_db("sqlite:///math_bank.db")
```

## 테스트

```bash
pytest tests/
```
