"""'대표이사(대표집행임원)변경' 수시공시를 모아 사장 교체일을 확정한다 → <data>/ceo_changes.json
   항목: {date(접수일), change_date(공시 본문 변경일자, 있으면), after(변경 후 대표이사), before(변경 전), raw}
   build_data.py가 사장(그룹 파견) 인물의 ceo_from(취임일)으로 쓴다."""
import json, re, time, urllib.request, urllib.parse, zipfile, io
from company import CFG, D, KEY, need_key, THIS_YEAR
need_key()
CORP = CFG["corp_code"]
def api(u): return json.loads(urllib.request.urlopen(u, timeout=60).read().decode("utf-8"))
rows = []
for y in range(max(2000, CFG["years"]["first"] - 2), THIS_YEAR + 1):
    q = urllib.parse.urlencode(dict(crtfc_key=KEY, corp_code=CORP, bgn_de=f"{y}0101", end_de=f"{y}1231", page_count=100))
    d = api("https://opendart.fss.or.kr/api/list.json?" + q)
    for f in d.get("list", []):
        nm = f["report_nm"].replace(" ", "")
        if "대표이사" in nm and "변경" in nm: rows.append(f)
    time.sleep(0.15)
out = []
for f in sorted(rows, key=lambda f: f["rcept_dt"]):
    rc = f["rcept_no"]; txt = ""
    try:
        b = urllib.request.urlopen("https://opendart.fss.or.kr/api/document.xml?" + urllib.parse.urlencode(dict(crtfc_key=KEY, rcept_no=rc)), timeout=120).read()
        z = zipfile.ZipFile(io.BytesIO(b))
        for n in z.namelist():
            raw = z.read(n)
            for enc in ("utf-8", "cp949"):
                try: txt += raw.decode(enc); break
                except Exception: pass
    except Exception as e: print("doc err", rc, e)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt.replace("&cr;", " ")))
    def grab(label):
        m = re.search(label + r"\s*[:：]?\s*(?:대표이사|사장|부사장|전무|상무)?\s*([가-힣]{2,4}|[가-힣]{2,3}\s[가-힣]{2,4})", t)
        return m.group(1).replace(" ", "") if m else ""
    after = grab(r"변경\s*후") or grab(r"신임\s*대표이사") or grab(r"선임\s*대표이사")
    before = grab(r"변경\s*전") or grab(r"퇴임\s*대표이사")
    cm = re.search(r"변경일자?\s*[:：]?\s*(\d{4})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})", t)
    change_date = f"{cm.group(1)}-{int(cm.group(2)):02d}-{int(cm.group(3)):02d}" if cm else None
    out.append({"date": f"{f['rcept_dt'][:4]}-{f['rcept_dt'][4:6]}-{f['rcept_dt'][6:]}", "change_date": change_date, "after": after, "before": before, "report_nm": f["report_nm"], "rcept_no": rc, "raw": t[:400]})
    print(out[-1]["date"], out[-1]["change_date"], before, "→", after, "|", f["report_nm"])
    time.sleep(0.3)
(D / "ceo_changes.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("saved", len(out))
