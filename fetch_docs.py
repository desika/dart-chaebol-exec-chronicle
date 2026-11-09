"""보고서 원문(document.xml zip) 수집 → <data>/docs/{사업연도}_{접수번호}[_{보고서코드}].xml
 1) exec_raw(구조화 API)에 있는 접수번호의 원문(사업보고서 + 분기·반기)
 2) API 이전 연도(설정 first ~ 2013 사업연도): list.json으로 그해 '사업보고서 (YYYY.12)' 접수번호를 찾아
    임원 표가 있는 가장 늦은 제출본을 저장. zip 안의 xml은 모두 이어 붙인다(본문이 첨부로 나뉜 옛 보고서 대응).
 인자: 연도 목록(선택). 없으면 설정 범위 전체."""
import json, sqlite3, urllib.request, urllib.parse, zipfile, io, pathlib, time, sys, re
from company import CFG, D, DB, KEY, need_key
need_key()
con = sqlite3.connect(DB); DOCS = D/"docs"; DOCS.mkdir(exist_ok=True)
years = [int(a) for a in sys.argv[1:]] or list(range(CFG["years"]["first"], CFG["years"]["last"] + 1))
def fetch_zip_xml(rc):
    b = urllib.request.urlopen("https://opendart.fss.or.kr/api/document.xml?" + urllib.parse.urlencode(dict(crtfc_key=KEY, rcept_no=rc)), timeout=120).read()
    z = zipfile.ZipFile(io.BytesIO(b))
    parts = [z.read(n) for n in sorted(z.namelist(), key=lambda n: (not n.lower().endswith(".xml"), len(n))) if n.lower().endswith(".xml")]
    return b"\n".join(parts)
def decode(raw):
    for enc in ("utf-8", "cp949", "euc-kr"):
        try: return raw.decode(enc)
        except Exception: pass
    return raw.decode("cp949", errors="replace")
def exec_table_rows(t):
    best = 0
    for m in re.finditer(r"<TABLE.*?</TABLE>", t, flags=re.S | re.I):
        n = re.sub(r"\s", "", re.sub(r"<[^>]+>", " ", m.group(0)))
        if "성명" in n and re.search(r"출생|생년", n) and re.search(r"주요경력|약력", n): best = max(best, len(re.findall(r"<TR", m.group(0), flags=re.I)))
    return best
# 1) API 접수번호
api_years = set()
for y, code, rc in con.execute("select distinct bsns_year, reprt_code, rcept_no from exec_raw order by 1,2"):
    if code == "11011": api_years.add(y)
    if code == "11011" and y not in years: continue
    if code != "11011" and y <= CFG["years"]["last"]: continue   # 과거 연도 분기 원문은 받지 않는다(API 등기임원으로 충분)
    dst = DOCS/(f"{y}_{rc}.xml" if code == "11011" else f"{y}_{rc}_{code}.xml")
    if dst.exists(): continue
    try: dst.write_bytes(fetch_zip_xml(rc)); print(y, code, rc, "saved", dst.stat().st_size)
    except zipfile.BadZipFile: print(y, rc, "not zip")
    time.sleep(0.4)
# 2) API 이전 연도: 열람 목록으로 사업보고서 찾기
checked_f = DOCS/"_checked_old.json"; checked = json.loads(checked_f.read_text(encoding="utf-8")) if checked_f.exists() else {}
for fy in years:
    if fy in api_years or fy >= 2014: continue
    if any(DOCS.glob(f"{fy}_*.xml")) or str(fy) in checked: continue
    fil = fy + 1
    q = urllib.parse.urlencode(dict(crtfc_key=KEY, corp_code=CFG["corp_code"], bgn_de=f"{fil}0101", end_de=f"{fil}1231", page_count=100))
    d = json.loads(urllib.request.urlopen("https://opendart.fss.or.kr/api/list.json?" + q, timeout=60).read().decode("utf-8"))
    reps = [f for f in d.get("list", []) if "사업보고서" in f["report_nm"] and (f"({fy}.12)" in f["report_nm"].replace(" ", "") or f"({fy}.12" in f["report_nm"])]
    if not reps: reps = [f for f in d.get("list", []) if "사업보고서" in f["report_nm"]]
    picked = None
    for f in sorted(reps, key=lambda f: f["rcept_dt"], reverse=True):   # 늦은 제출본(정정) 우선, 임원 표 있는 것
        try: raw = fetch_zip_xml(f["rcept_no"])
        except zipfile.BadZipFile: continue
        rows = exec_table_rows(decode(raw)); time.sleep(0.4)
        if rows > 0: picked = (f, raw, rows); break
        if picked is None: picked = (f, raw, 0)
    if picked:
        f, raw, rows = picked; dst = DOCS/f"{fy}_{f['rcept_no']}.xml"; dst.write_bytes(raw)
        print(fy, f["rcept_dt"], f["report_nm"], "임원표 행", rows, "→", dst.name)
    else: print(fy, "사업보고서 없음")
    checked[str(fy)] = {"filings": len(reps), "picked": picked[0]["rcept_no"] if picked else None, "rows": picked[2] if picked else 0}
    checked_f.write_text(json.dumps(checked, ensure_ascii=False, indent=1), encoding="utf-8"); time.sleep(0.2)
print("docs:", len(list(DOCS.glob("*.xml"))))
