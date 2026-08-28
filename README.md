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

텍스트 레이어가 없는 스캔 PDF(`pdf_ocr_problem_extract.py`)를 다루려면 별도로
[Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) 설치가 추가로
필요하다(pip으로 안 들어오는 시스템 프로그램). 한국어 인식을 쓰려면
`tessdata_best` 저장소의 `kor.traineddata`를 받아서 tessdata 폴더에 넣어야
한다(기본 `tessdata` 저장소 모델은 이 자료 폰트에서 정확도가 크게 떨어졌음).

자동 출제(`generate_worksheet.py`)로 HWP 시험지를 생성하려면 이 PC에 한글
(HWP) 프로그램이 설치되어 있어야 한다(COM 자동화로 실제 문서를 생성함,
Windows 전용). HTML 시험지만 필요하면 `--html-only`로 이 의존성을 건너뛸
수 있다.

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

```bash
python generate_worksheet.py --chapter 미적분1 --subsection "도함수의 활용 ⑵" \
    --type "함수의 극대" --count 10 --title "도함수의 활용 소단원 평가" \
    --out worksheets/deriv_app2
# worksheets/deriv_app2.html (인쇄/열람용) 과 .hwp (실제 편집 가능한 수식 포함) 를 함께 생성.
```

```bash
# A형/B형 두 버전(문제·보기 순서를 각각 다르게 섞음), 난이도 하:중:상 = 2:5:3
# 비율로 20문제, 정답은 별도 파일로 분리
python generate_worksheet.py --chapter 미적분1 --count 20 \
    --label-ratio "하:2,중:5,상:3" --form A --form B --separate-answer-key \
    --title "중간고사 대비" --out worksheets/midterm
# worksheets/midterm_A.html, midterm_A.hwp, midterm_A_answers.html, midterm_A_answers.hwp
# (B형도 동일하게) 를 생성. 보기를 섞어도 정답 표시(①②③...)는 실제 정답 내용을 계속 가리키도록 자동으로 다시 계산된다.
```

## 테스트

```bash
pytest tests/
```
