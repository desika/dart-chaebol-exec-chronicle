# companies/<slug>/ — 회사별 설정과 데이터

이 폴더의 내용은 git에 올라가지 않습니다(`.gitignore`). `add_company.py`가 `config.json`과 `data/group_map.json`을 만들고, 나머지 `data/*`는 파이프라인이 채웁니다.

## config.json

| 키 | 뜻 | 예 |
|---|---|---|
| `slug`, `name`, `corp_code`, `stock` | 폴더명, DART 회사명, 고유번호(8자리), 종목코드 | |
| `db` | SQLite 파일명 | `lginnotek_exec.db` |
| `logo` | 머리글 로고 파일명(이 폴더 안) | `logo.svg` |
| `self_regex` | 자사 표기(전신·영문 포함). 경력 문구에서 자사 보직 판별, 보직 앞 회사명 제거 | `LG이노텍\|LG Innotek` |
| `group_regex` | 그룹 계열사 표기(자사 제외). 계열사 출신·그룹 전입 판정 | `LG(?!이노텍)\|엘지\|GS` |
| `group_companies_regex` | 계열사 회사명 목록(전 직장 추적용) | |
| `group_name` | 그룹 이름(표시용). 없으면 "그룹" | `LG` |
| `title_merge_year` | 전무→부사장 통합 인사 연도. 승진 표식을 통합 전/후로 구분. 없으면 구분 안 함 | `2021` |
| `secom` | 외국 합작사 파견 임원(일본식 이름·비상근) 트랙을 따로 둘지 | `false` |
| `years.first`, `years.last` | 사업연도 범위 | `2016`, `2025` |
| `years.quarters` | 추가로 수집할 당해 연도 분기 `[연도, 코드]` (11013 1분기, 11012 반기, 11014 3분기) | `[[2026,"11013"],[2026,"11012"]]` |
| `years.quarters_from` | 과거 분기보고서 수집 시작 연도(기본 2015) | `2016` |
| `years.pay_first` | 보수 API 시작 연도(기본 2015) | |
| `sector_rules` | 부문 판정 `[이름, 정규식]` 목록(첫 매치) | `[["건설부문","^건설\|건설부문"], …]` |
| `sector_from_job` | 담당업무 접두어로 부문 판정(부문별 대표 체제) | `true` |
| `sector_label` | 부문 칸 이름 | `부문`, `사업 영역(추정)` |
| `sector_scope` | 부문 버튼으로 한 부문씩 보기 | `true` |
| `sector_default` | 기본 부문 | `건설부문` |
| `sector_overrides` | 이름별 부문 강제 지정 | `{"홍길동":"상사부문"}` |
| `ext_hint_regex` | 외부 경력으로 볼 어휘 추가(기본: 은행·증권·관청·대학 등) | |
| `affiliates` | 자회사 `{이름: corp_code}`. 넣으면 자회사 임원 임기표·예측 보드 | |
| `affiliate_rules` | 자회사별 `{size: "부사장급"\|"상무급", fit: 담당 적합 정규식}` | |
| `affiliate_hint` | 아직 수집하지 않은 자회사 후보(표시용) | |
| `events` | 생애선에 표시할 연도 이벤트 `{year,label,kind}` | |
| `first_doc` | 공시 원문 최초 시점(표시용) | `"1998년 사업보고서"` |
| `origin_scan` | 전 직장 추적 범위(표시용) `{scanned:[], not_available:[]}` | |

## data/group_map.json

"선임 당시 보직 → 출신 그룹" 규칙입니다. 위에서부터 첫 매치.

```json
{
 "rules": [{"match": "정보보호|보안|IT|전산", "group": "IT·정보보호"}, {"match": "영업|지점|지사", "group": "영업"}],
 "overrides": {"홍길동": "경영지원·재무"},
 "track_overrides": {"홍길동": "그룹 전입 임원"}
}
```

편집 후 `set COMPANY=<slug>` 하고 `python build_data.py && python build_affil.py && python render_app.py`.

## data/ 산출물

`exec_raw.json`(임원현황 원시), `exec_doc.json`(원문 표 파싱), `persons.json/csv`(인물 마스터), `pay_raw.json`, `pay_detail.json`, `ceo_changes.json`, `app_data.json`(앱 데이터), `affil.json`, `docs/`(보고서 원문 xml), `<slug>_exec.db`(SQLite).
