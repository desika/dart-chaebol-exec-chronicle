"""자회사 공시 수집(설정 affiliates: {회사명: corp_code}): 감사보고서(대표이사명), 임원의변동, 대규모기업집단현황공시(연1회·개별회사: 임원 명단)
   → <data>/affil_raw.json  (표는 셀 배열 그대로 저장, 해석은 build_affil.py). affiliates 가 비어 있으면 아무것도 하지 않는다."""
import json, time, urllib.request, urllib.parse, pathlib, re, zipfile, io, sys
from company import CFG, D, KEY, need_key, THIS_YEAR
COMPANIES = CFG.get("affiliates") or {}
if not COMPANIES: print("affiliates 설정 없음 → 자회사 수집 생략"); sys.exit(0)
need_key(); DOC = D/"docs_affil"; DOC.mkdir(exist_ok=True)
def api(u): return json.loads(urllib.request.urlopen(u, timeout=120).read().decode("utf-8"))
def filings(code):
    out = []; page = 1
    while True:
        q = urllib.parse.urlencode(dict(crtfc_key=KEY, corp_code=code, bgn_de="20100101", end_de=f"{THIS_YEAR}1231", page_count=100, page_no=page))
        d = api(f"https://opendart.fss.or.kr/api/list.json?{q}"); out += d.get("list", [])
        if page >= int(d.get("total_page", 1)): break
        page += 1
    return out
def doc(rc):
    q = urllib.parse.urlencode(dict(crtfc_key=KEY, rcept_no=rc)); b = urllib.request.urlopen(f"https://opendart.fss.or.kr/api/document.xml?{q}", timeout=180).read()
    z = zipfile.ZipFile(io.BytesIO(b)); out = {}
    for n in z.namelist():
        raw = z.read(n)
        for enc in ("utf-8", "cp949"):
            try: out[n] = raw.decode(enc); break
            except Exception: pass
    return out
def cells(tr): return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c.replace("&cr;", " "))).strip() for c in re.findall(r"<T[HD][^>]*>.*?</T[HD]>", tr, flags=re.S | re.I)]
def tables(t):
    for tb in re.findall(r"<TABLE.*?</TABLE>", t, flags=re.S | re.I):
        rows = [cells(tr) for tr in re.findall(r"<TR.*?</TR>", tb, flags=re.S | re.I)]
        rows = [r for r in rows if r]
        if rows: yield rows
out = {"companies": {}, "filings": []}
for cname, code in COMPANIES.items():
    fl = filings(code); out["companies"][cname] = {"corp_code": code, "n_filings": len(fl)}
    print(cname, len(fl))
    for f in fl:
        nm = f["report_nm"]; kind = None
        if "감사보고서" in nm and "연결" not in nm: kind = "audit"
        elif "임원의변동" in nm or "임원의 변동" in nm: kind = "exec_change"
        elif "대규모기업집단현황공시" in nm and "연1회" in nm: kind = "annual_group"
        elif "사업보고서" in nm: kind = "annual_report"
        if not kind: continue
        rc = f["rcept_no"]; cached = DOC/f"{cname}_{kind}_{rc}.json"
        if cached.exists(): rec = json.loads(cached.read_text(encoding="utf-8"))
        else:
            try: d = doc(rc)
            except Exception as e: print("  ERR", rc, e); continue
            rec = {"company": cname, "kind": kind, "rcept_no": rc, "rcept_dt": f["rcept_dt"], "report_nm": nm, "files": {}}
            for n, t in d.items():
                txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t.replace("&cr;", " ")))
                ceo = re.findall(r"대표이사\s*[:：]?\s*([가-힣]{2,4})\b", txt)
                tb = [rows for rows in tables(t) if any(re.search(r"(선임일|임원명|직위|변경전|대표자)", c) for c in rows[0])]
                rec["files"][n] = {"len": len(txt), "ceo_mentions": ceo[:10], "tables": tb}
            cached.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8"); time.sleep(0.3)
        out["filings"].append(rec)
        print("  ", kind, f["rcept_dt"], nm, sum(len(v["tables"]) for v in rec["files"].values()), "tables")
(D/"affil_raw.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("filings", len(out["filings"]))
