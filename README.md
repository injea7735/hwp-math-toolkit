# hwp-math-toolkit

수학 문제은행 구축을 위한 작은 도구 모음.

## 구성

- **`hwp_eq_to_latex.py`** — 한글(HWP) 수식 편집기 스크립트(DSL)를 LaTeX로 변환하는 파서.
  `^`, `_`, `over`, `sqrt`, `bar`, `rm`, `LEFT`/`RIGHT` 등 자주 쓰이는 수식 표현을 지원한다.
- **`models.py`** — 문제은행 DB 스키마 초안(SQLAlchemy ORM). 대단원/중단원/소단원/유형(taxonomy)과
  개념(Concept) 태그, 문제(Problem), 출처(Source)를 다룬다.
- **`import_from_ngd.py`** — NGD 문제은행 앱(`exam.db`, SQLite)에서 문제를 읽어와 위 스키마로 가져오는 임포터.
  NGD의 평평한 unit 목록은 "NGD 가져오기" 아래 소단원/유형으로 placeholder 매핑되며, 재실행해도
  이미 가져온 문제(`ngd_problem_id`)는 건너뛴다.

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

```bash
python import_from_ngd.py --target sqlite:///math_bank.db
# 기본적으로 %LOCALAPPDATA%\examtool\exam.db 를 읽는다. 다른 경로는 --ngd-db 로 지정.
```

## 테스트

```bash
pytest tests/
```
