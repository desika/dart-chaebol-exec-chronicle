"""회사별 설정 로더. 환경변수 COMPANY=<slug> 로 companies/<slug>/config.json 을 읽는다(설정은 add_company.py 가 만든다).
   데이터는 companies/<slug>/data/ 에 쌓인다."""
import os, json, pathlib, datetime, sys
from dart_key import KEY, need_key
ROOT = pathlib.Path(__file__).resolve().parent
SLUG = os.environ.get("COMPANY", "")
if not SLUG: sys.exit("환경변수 COMPANY=<slug> 가 필요하다. 처음이면 python add_company.py <회사명> 으로 시작")
CDIR = ROOT / "companies" / SLUG
if not (CDIR / "config.json").exists(): sys.exit(f"{CDIR / 'config.json'} 없음. python add_company.py <회사명> --slug {SLUG}")
CFG = json.loads((CDIR / "config.json").read_text(encoding="utf-8"))
D = CDIR / "data"; D.mkdir(parents=True, exist_ok=True)
DB = D / CFG.get("db", "exec.db")
SELF_RX = CFG["self_regex"]                      # 자사 표기(경력 문구에서 자사 보직 판별)
SELF_PFX = rf"^(?:{SELF_RX})\s*"                 # 보직 앞의 자사명 제거용
GROUP_RX = CFG["group_regex"]                    # 그룹 계열사(자사 제외) 표기 → 계열사 출신 판정
GROUP_NAME = CFG.get("group_name", "")           # 그룹 이름(표시용, 없으면 "")
TODAY = datetime.date.today(); THIS_YEAR = TODAY.year
NOW_DEC = round(THIS_YEAR + (TODAY.month - 0.8) / 12, 2)   # 올해를 소수 연도로(생애선 오른쪽 끝)
