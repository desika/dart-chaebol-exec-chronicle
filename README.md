# dart-exec-chronicle — DART 공시로 복원하는 한국 상장사 임원 생애

> Rebuilds the career timeline of every executive of a Korean listed company (appointment → promotions → retirement, education, origin unit, pay, severance, CEO succession) purely from public DART (Korea's electronic disclosure system) filings, and renders it as a single self-contained HTML file. Pure Python standard library, no dependencies. Input: a company name. Output: one HTML file.

회사 이름 하나를 넣으면 금융감독원 전자공시(DART)의 임원현황·보수·사업보고서 원문·대표이사 변경 공시를 모아, 그 회사 임원 전원의 생애(선임 → 승진 → 퇴임), 학력·동문, 출신 보직, 보수·퇴직금, 사장 계보를 복원하고 **단일 HTML 파일(임원 도감)** 로 만들어 줍니다. 서버 없이 더블클릭으로 열립니다.

이 저장소에는 **엔진 코드만** 있습니다. 특정 회사의 설정·수집 데이터·산출물은 포함하지 않으며(`companies/`, `dist/`는 git 제외), 실행하는 사람이 자기 DART 인증키로 직접 만듭니다.

## 빠른 시작

요구 사항: Python 3.10 이상. 외부 패키지 없음. (렌더 검사 `check_app.py`만 Windows의 Edge를 씁니다. 선택 사항)

```
# 1) DART 인증키 (https://opendart.fss.or.kr 에서 무료 발급)
set DART_API_KEY=발급받은키          # macOS/Linux: export DART_API_KEY=...
#    또는 저장소 루트에 dart_key.txt 파일로 저장 (git 제외됨)

# 2) 회사 한 줄
set PYTHONUTF8=1                     # Windows 콘솔 한글
python add_company.py LG이노텍
```

끝나면 `dist/App_LG이노텍_<버전>.html` 이 생깁니다. 최근 10년(2016 사업연도~)을 기본으로 수집하며, 보고서 수에 따라 5~20분 걸립니다.

### add_company.py 옵션

| 옵션 | 뜻 | 예 |
|---|---|---|
| `이름` 또는 `corp_code` | DART 회사명(부분 일치, 상장사 우선) 또는 8자리 고유번호 | `삼성E&A`, `00126308` |
| `--slug` | 폴더 이름(영문). 없으면 영문 회사명에서 자동 | `--slug sena` |
| `--group` | 그룹 프리셋(삼성·LG·SK·현대·롯데·한화·CJ·none). 회사명이 그룹명으로 시작하면 자동 | `--group 삼성` |
| `--self` | 자사의 전신·별칭(경력 문구에서 자사 보직으로 인식, 계열사 목록에서 제외) | `--self 삼성엔지니어링` |
| `--first` | 첫 사업연도(기본 2016) | `--first 2010` |
| `--logo` | 머리글 로고 파일(선택) | `--logo logo.svg` |
| `--no-fetch` | 수집 생략, 파싱·빌드·렌더만 다시 | |

회사명이 바뀐 회사(예: 삼성엔지니어링 → 삼성E&A)는 DART 고유번호가 같으므로 현재 이름으로 넣고 옛 이름을 `--self`에 적어 주면 됩니다.

## 무엇이 만들어지나

단일 HTML 안에 7개 화면이 들어 있습니다.

| 화면 | 내용 |
|---|---|
| 생애선 | 임원 전원의 재임 막대(사장·그룹 전입·내부 성장 섹션). 직위별 색, 직위 연차별 농도, 승진 표식, 퇴직금 공시 표식. 이름 옆에 생년·만 나이·직위 연차 |
| 명부 | 정렬·필터 되는 표(출생·구분·현직위·담당·선임일·퇴임·연차·출신 그룹·부문·학교·학위·보수 공시 횟수) |
| 개인 도감 | 연도별 공시 변화, 경력 궤적, 승진 이력, 보수·퇴직금 산정기준, 같은 자리를 거친 사람, 선임 동기, 동문 |
| 출신·스펙 | 선임연도 × 출신 그룹 교차표, 선임 나이·학위·지역·학교·전공 분포 |
| 보수·퇴직금 | 개인별 보수 공시, 퇴직소득 × 임원 근무연수, 이사·감사 보수 총액, 직원 현황 |
| 관계망 | 대학 동문(같은 학교 + 같은 과정만. 학사끼리·석사끼리·MBA끼리), 같이 다녔을 가능성 표시, 해외/국내 대학 구분 |
| 자료·규칙 | 출처, 판정 규칙, 연도별 직위 인원, 한계 |

부문별 대표 체제인 회사(건설·상사·패션 같은 사업부문)는 설정 `sector_scope`를 켜면 제목 아래 부문 버튼이 생기고 한 부문씩 봅니다. 자회사 임원(대표이사·감사) 임기표와 다음 대표 예측 보드는 설정 `affiliates`에 자회사 고유번호를 넣으면 붙습니다.

## 파이프라인

`add_company.py`가 아래를 순서대로 실행합니다. 각 단계는 환경변수 `COMPANY=<slug>`를 주고 따로 실행할 수도 있습니다.

| 단계 | 스크립트 | 입력 → 출력 |
|---|---|---|
| 수집 | `fetch_dart.py` | 임원현황 API `exctvSttus`(사업보고서 + 모든 분기·반기) → `exec_raw.json`, SQLite |
| 수집 | `fetch_docs.py` | 보고서 원문 `document.xml`(zip) → `docs/*.xml`. 2013년 이전은 `list.json`으로 사업보고서 탐색 |
| 수집 | `fetch_pay.py` | 보수 API 5종 → `pay_raw.json` |
| 수집 | `fetch_ceo_changes.py` | '대표이사 변경' 수시공시 → `ceo_changes.json` |
| 수집 | `fetch_affiliates.py` | (설정 시) 자회사 감사보고서·임원의변동·기업집단현황 → `affil_raw.json` |
| 파싱 | `parse_exec_docs.py` | 원문 임원현황 표 → 미등기임원 복원, `exec_raw`에 병합 |
| 파싱 | `parse_pay.py` | 원문 '개인별 보수지급금액 산정기준' 표 → `pay_detail.json` |
| 분석 | `analyze.py` | 인물 단위 병합(이름 + 출생연월), 선임일·퇴임·학력·경력 파싱 → `persons.json/csv` |
| 빌드 | `build_data.py` | 트랙·출신 그룹·부문·사장 계보·동문 엣지·이벤트 → `app_data.json` |
| 빌드 | `build_affil.py` | 사장 임기표, 자회사 임기표·예측 보드 → `affil.json` |
| 렌더 | `render_app.py` | `app_template.html` + 데이터 → `dist/App_<회사>_<버전>.html` |
| 검사 | `check_app.py` | 헤드리스 Edge로 전원 상세 + 7개 탭 호출, JS 오류 확인 |

`careerlib.py`는 경력 문구 파서(학교·전공·학위 추출, 한 덩어리 경력 분리)이고 `company.py`가 설정을 읽습니다.

## 만든 뒤 할 일: 그루핑 교정

`companies/<slug>/data/group_map.json` 이 "선임 당시 보직 → 출신 그룹" 규칙입니다. 처음엔 범용 규칙(영업·R&D·경영지원 등 12개)이라 그 회사 조직 어휘가 빠져 '미분류'가 남습니다. `add_company.py` 마지막에 미분류 목록이 찍히니 규칙(`rules`, 위에서부터 첫 매치)이나 이름별 `overrides`를 추가하고 다시 빌드합니다.

```
set COMPANY=lginnotek
python build_data.py && python build_affil.py && python render_app.py
```

`companies/<slug>/config.json`의 항목은 [companies/README.md](companies/README.md)에 있습니다(자사·그룹 표기 정규식, 연도 범위, 부문 규칙, 자회사, 이벤트 등).

## 판정 규칙(요약)

- **동일 인물** = 이름(공백 제거) + 출생연월. 출생월 오기는 병합 규칙으로 흡수.
- **임원 선임일** = 보고서들의 재직기간 시작일 중 가장 이른 날짜. 없으면 첫 공시 연도 말로 추정(≤ 표시).
- **퇴임** = 퇴직소득이 공시된 보고서 연도가 마지막 등장 보고서 연도와 같으면 그해 12월, 다르면 1월. 공시가 없으면 마지막 등장 연도 12월. 분기보고서까지 수집해 연중 취임·퇴임을 분기 단위로 좁힘.
- **사장** = 자사 대표이사(직위 또는 담당업무 시작, '대표이사 보좌역' 제외) 또는 대표이사 변경 공시. 임기 종료 = 후임 취임일. 공동대표 체제는 개인별.
- **트랙** = 사장(그룹 파견 / 내부 승진) · 그룹 전입 임원 · 내부 성장 임원 · 사외이사·감사.
- **직위 연차** = 마지막 승진 인사연도 기준(사장은 취임 기준). 삼성 계열은 2021-12 전무 폐지를 반영(`title_merge_year`).
- **동문** = 같은 학교 + 같은 과정. 고졸은 잇지 않음. 졸업연도 차이가 과정 길이 안이면 '같이 다녔을 듯'.

자세한 규칙과 예외는 앱의 '자료·규칙' 탭과 코드 주석에 있습니다.

## 한계

- 사업보고서가 적은 회사(비상장·소규모)는 복원 범위가 좁습니다. 미등기임원은 회사에 따라 원문에만 있습니다.
- 재직기간을 "N년 M개월"로만 적는 회사는 선임일이 추정값(≤)이 됩니다.
- 입사연도·팀장 임명연도·고과는 공시되지 않습니다. 출신 그룹·부문은 문구 기반 추정입니다.
- 5억 원 미만 보수는 개인별 공시가 없어 상무급 퇴직금은 대부분 보이지 않습니다.
- 그룹 프리셋은 7개 그룹만 있습니다. 다른 그룹은 `--group none`으로 만들고 설정의 `group_regex`를 직접 채우면 됩니다.

## 데이터에 관하여

이 도구는 DART에 공개된 정기·수시공시만 읽습니다. 저장소에는 코드만 있고, 실행 결과(설정·수집 데이터·HTML)는 각자 로컬에 남습니다(`.gitignore`). 결과물을 공유할 때의 판단은 사용하는 사람의 몫입니다.

## 방향과 참여

여러 회사의 임원 생애 데이터를 같은 규칙으로 쌓아 한국 대기업 임원의 승진·퇴임 패턴을 학습하는 모델(선임 나이·연차·출신·학력에 따른 승진·퇴임 확률)을 만드는 것이 다음 단계입니다. 이슈·PR을 환영합니다.

- 회사별 `group_map.json` 어휘 규칙, 그룹 프리셋 추가
- 사업보고서 원문 표 형식(옛 보고서, 비정형 머리글) 파서 보강
- 재직기간·학력 문구 파싱 예외
- 모델(특징 설계, 학습 스크립트)

## 라이선스

MIT. [LICENSE](LICENSE)
