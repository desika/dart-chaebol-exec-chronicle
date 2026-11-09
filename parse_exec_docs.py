"""사업보고서 원문(data/docs/*.xml)의 임원현황 표를 직접 파싱해 미등기임원까지 복원.
   API(exctvSttus)는 2014~2020년에 등기임원만 주지만 원문에는 상무 이상 전원이 있다.
   결과: data/exec_doc.json + SQLite exec_raw 테이블에 API에 없는 (연도,이름,출생) 행 추가(src='doc')."""
import pathlib, re, json, sqlite3
from company import CFG, D, DB
CO = CFG["name"]
def load(f):
    raw = f.read_bytes()
    for enc in ("utf-8", "cp949"):
        try: return raw.decode(enc)
        except Exception: pass
    return raw.decode("utf-8", errors="replace")
def cells(tr): return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c.replace("&cr;", "\n"))).strip() for c in re.findall(r"<T[HDEU][^>]*>.*?</T[HDEU]>", tr, flags=re.S | re.I)]
HDR_KEYS = {"성명": "nm", "성별": "sexdstn", "출생년월": "birth_ym", "생년월일": "birth_ym", "직위": "ofcps", "직명": "ofcps", "직명(상근여부)": "ofcps_fte", "성명(생년월일)": "nm_birth",
            "등기임원여부": "rgist_exctv_at", "상근여부": "fte_at", "담당업무": "chrg_job", "주요경력": "main_career", "약력": "main_career", "학력": "edu",
            "재직기간": "hffc_pd", "임기만료일": "tenure_end_on", "최대주주와의관계": "mxmm_shrholdr_relate"}
def norm_birth(s):
    """'1958년 03월' / '1958.03' / ''58.03.17' / '1958년 03월 17일' → '1958년 03월'"""
    s = (s or "").strip()
    m = re.search(r"(\d{4})\s*[년.\-/]\s*(\d{1,2})", s)
    if m: return f"{m.group(1)}년 {int(m.group(2)):02d}월"
    m = re.search(r"^['`‘’]?(\d{2})\s*[.\-/]\s*(\d{1,2})", s)
    if m: y = int(m.group(1)); return f"{1900 + y if y > 30 else 2000 + y}년 {int(m.group(2)):02d}월"
    return s
def is_exec_table(tbc):
    """임원현황 표 판별: 성명 + 출생/생년 + 경력(주요경력|약력) + 직위/직명"""
    n = re.sub(r"\s", "", tbc)
    return ("성명" in n) and re.search(r"출생|생년", n) and re.search(r"주요경력|약력", n) and re.search(r"직위|직명", n)
out = []
for f in sorted(D.glob("docs/20*_*.xml")):
    parts = f.stem.split("_"); year = int(parts[0]); rcept = parts[1]; code = parts[2] if len(parts) > 2 else "11011"; t = load(f)
    stlm = {"11011": f"{year}-12-31", "11012": f"{year}-06-30", "11013": f"{year}-03-31", "11014": f"{year}-09-30"}[code]
    # 본문 'VIII. 임원 및 직원 등에 관한 사항' 이후의 표만 (그 앞의 최대주주(법인) 임원 표 제외)
    sec = 0
    for hm in re.finditer(r"임원\s*및\s*직원\s*등에\s*관한\s*사항|임원\s*및\s*직원의\s*현황", t):
        if re.search(r"(등기임원|임원)\s*현황", t[hm.end():hm.end() + 6000]): sec = hm.start(); break
    tables = [m for m in re.finditer(r"<TABLE.*?</TABLE>", t, flags=re.S | re.I) if m.start() >= sec]
    for i, m in enumerate(tables):
        tb = m.group(0); tbc = re.sub(r"<[^>]+>", " ", tb.replace("&cr;", " "))
        if not is_exec_table(tbc): continue
        hdr_rows = [cells(tr) for tr in re.findall(r"<TR.*?</TR>", tb, flags=re.S | re.I)]
        hdr = [re.sub(r"\s", "", c) for c in hdr_rows[0]]
        # 헤더 → 열 인덱스 (소유주식수는 2열 차지)
        cols = []
        for hname in hdr:
            if hname in ("소유주식수", "소유주식"): cols += ["stk1", "stk2"]
            else: cols.append(HDR_KEYS.get(hname, hname))
        if "nm" not in cols and "nm_birth" not in cols: continue
        # 본문: 같은 테이블 안의 나머지 행 또는 다음 TABLE
        body_rows = [r for r in hdr_rows[1:] if len(r) >= len(cols) - 1]
        if not body_rows and i + 1 < len(tables):
            body_rows = [cells(tr) for tr in re.findall(r"<TR.*?</TR>", tables[i + 1].group(0), flags=re.S | re.I)]
        for r in body_rows:
            if len(r) < 6: continue
            rec = {k: (r[j] if j < len(r) else "") for j, k in enumerate(cols)}
            rec = {k: v for k, v in rec.items() if k not in ("stk1", "stk2")}
            # 옛 형식 보정
            if "nm_birth" in rec:
                nb = rec.pop("nm_birth"); mb = re.match(r"^\s*([가-힣A-Za-z· ]{2,12}?)\s*\(\s*([\d'`‘’.\-/년월일 ]{4,})\)\s*$", nb)
                if mb: rec["nm"], rec["birth_ym"] = mb.group(1), mb.group(2)
                elif re.match(r"^[가-힣A-Za-z· ]{2,12}$", nb.strip()): rec["nm"], rec["birth_ym"] = nb.strip(), ""   # 생년월일 미기재
                else: continue
            if "ofcps_fte" in rec:
                of = rec.pop("ofcps_fte"); mf = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", of)
                if mf:
                    rec["ofcps"] = mf.group(1).strip(); inner = mf.group(2)
                    rec["fte_at"] = "비상근" if "비상근" in inner else ("상근" if "상근" in inner else rec.get("fte_at", ""))
                    if not rec.get("rgist_exctv_at"): rec["rgist_exctv_at"] = "미등기임원" if "비등기" in inner else ("등기임원" if "등기" in inner else "")
                elif of.strip() in ("상근", "비상근"): rec["fte_at"] = of.strip(); rec["ofcps"] = "미기재"   # 2002~2003 사업연도: 직명 칸에 상근여부만 기재
                else: rec["ofcps"] = of.strip()
            if "edu" in rec:
                e = rec.pop("edu")
                if e and e not in ("-", ""): rec["main_career"] = (rec.get("main_career", "") + "\n" + e).strip()
            nm = re.sub(r"\s+", "", rec.get("nm", ""))
            if not re.match(r"^[가-힣A-Za-z·]{2,12}$", nm) or nm in ("성명",): continue
            rec["nm"] = nm; rec["birth_ym"] = norm_birth(rec.get("birth_ym", ""))
            rec.update(bsns_year=year, reprt_code=code, rcept_no=rcept, corp_name=CO, src="doc", stlm_dt=stlm)
            out.append(rec)
seen=set(); dedup=[]
for rec in out:
    k=(rec["bsns_year"], rec["reprt_code"], re.sub(r"\s+","",rec["nm"]), re.sub(r"\s+","",rec.get("birth_ym","")))
    if k in seen: continue
    seen.add(k); dedup.append(rec)
out=dedup
(D / "exec_doc.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
# SQLite 병합
con = sqlite3.connect(DB)
cols_db = [c[1] for c in con.execute("pragma table_info(exec_raw)")]
if "src" not in cols_db: con.execute("alter table exec_raw add column src text default 'api'")
def norm(s): return re.sub(r"\s+", "", s or "")
con.execute("delete from exec_raw where src='doc'"); con.commit()   # 재파싱: 기존 원문 행 제거 후 다시 넣는다
have = {(r[0], r[1], norm(r[2]), norm(r[3])) for r in con.execute("select bsns_year, reprt_code, nm, birth_ym from exec_raw")}
added = 0
for rec in out:
    k = (rec["bsns_year"], norm(rec["nm"]), norm(rec["birth_ym"]).replace(".", "년") )
    # API 형식 '1968년 02월' vs 원문 '1968.02' 정규화 비교
    kb = re.sub(r"(\d{4})\.(\d{2})", r"\1년\2월", norm(rec["birth_ym"]))
    if (rec["bsns_year"], rec["reprt_code"], norm(rec["nm"]), kb) in have: continue
    con.execute("insert into exec_raw (bsns_year,reprt_code,rcept_no,corp_name,nm,sexdstn,birth_ym,ofcps,rgist_exctv_at,fte_at,chrg_job,main_career,mxmm_shrholdr_relate,hffc_pd,tenure_end_on,stlm_dt,src) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rec["bsns_year"], rec["reprt_code"], rec["rcept_no"], CO, rec["nm"], rec.get("sexdstn", ""), re.sub(r"(\d{4})\.(\d{2})", r"\1년 \2월", rec.get("birth_ym", "")), rec.get("ofcps", ""), rec.get("rgist_exctv_at", ""), rec.get("fte_at", ""), rec.get("chrg_job", ""), rec.get("main_career", ""), rec.get("mxmm_shrholdr_relate", ""), rec.get("hffc_pd", ""), rec.get("tenure_end_on", ""), rec["stlm_dt"], "doc"))
    added += 1
con.commit()
by = {}
for rec in out: by.setdefault(rec["bsns_year"], 0); by[rec["bsns_year"]] += 1
con.row_factory = sqlite3.Row
allrows = [dict(r) for r in con.execute("select * from exec_raw")]
(D / "exec_raw.json").write_text(json.dumps(allrows, ensure_ascii=False, indent=1), encoding="utf-8")
print("doc rows", len(out), "by year", by, "| added to db", added)
