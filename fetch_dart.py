"""DART 임원현황(exctvSttus) 수집: 사업보고서 + 분기·반기 → <data>/exec_raw.json + SQLite exec_raw"""
import json, sqlite3, time, urllib.request, urllib.parse, pathlib
from company import CFG, D, DB, KEY, need_key
need_key()
API = "https://opendart.fss.or.kr/api/exctvSttus.json"
CORP = CFG["corp_code"]
# 사업보고서 11011, 1분기 11013, 반기 11012, 3분기 11014
QF = max(CFG["years"]["first"], CFG["years"].get("quarters_from", 2015))   # 분기 구조화 API는 2015년부터
REPORTS = [(y, "11011") for y in range(CFG["years"]["first"], CFG["years"]["last"] + 1)] + [(y, c) for y in range(QF, CFG["years"]["last"] + 1) for c in ("11013", "11012", "11014")] + [tuple(q) for q in CFG["years"]["quarters"]]
out = D
rows = []
for year, rc in REPORTS:
    q = urllib.parse.urlencode(dict(crtfc_key=KEY, corp_code=CORP, bsns_year=year, reprt_code=rc))
    d = json.loads(urllib.request.urlopen(f"{API}?{q}", timeout=30).read().decode("utf-8"))
    lst = d.get("list", [])
    print(year, rc, d.get("status"), d.get("message"), len(lst))
    for r in lst:
        r["bsns_year"] = year; r["reprt_code"] = rc
        rows.append(r)
    time.sleep(0.3)
(out / "exec_raw.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
con = sqlite3.connect(DB)
con.execute("drop table if exists exec_raw")
cols = ["bsns_year","reprt_code","rcept_no","corp_name","nm","sexdstn","birth_ym","ofcps","rgist_exctv_at","fte_at","chrg_job","main_career","mxmm_shrholdr_relate","hffc_pd","tenure_end_on","stlm_dt"]
con.execute(f"create table exec_raw ({','.join(cols)})")
con.executemany(f"insert into exec_raw values ({','.join('?'*len(cols))})", [[r.get(c) for c in cols] for r in rows])
con.commit(); print("saved", len(rows))
