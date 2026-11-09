"""사업보고서 원문에서 개인별 보수 산정기준 표(이름|보수종류|총액|산정기준) 추출 → data/pay_detail.json"""
import pathlib, re, json
from company import D
def cells(tr): return [re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",c)).strip() for c in re.findall(r"<T[HD].*?</T[HD]>",tr,flags=re.S|re.I)]
out=[]
for f in sorted((D/"docs").glob("*.xml")):
    year=int(f.name[:4]); raw=f.read_bytes()
    m=re.search(rb'encoding="([^"]+)"',raw[:300]); enc=(m.group(1).decode() if m else "utf-8")
    try: t=raw.decode(enc)
    except Exception: t=raw.decode("cp949",errors="replace")
    for tb in re.findall(r"<TABLE.*?</TABLE>",t,flags=re.S|re.I):
        if "퇴직소득" not in tb or "산정기준" not in tb: continue
        rows=[cells(r) for r in re.findall(r"<TR.*?</TR>",tb,flags=re.S|re.I)]
        rows=[r for r in rows if r]
        if not rows or not any("이름" in c for c in rows[0]): continue
        recs=[]; rec=None
        for r in rows[1:]:
            if len(r)>=5:
                nm=r[0].replace("&cr;"," ")
                rec={"year":year,"name":nm.split()[-1] if len(nm.split())>1 else nm,"ofcps":" ".join(nm.split()[:-1]) if len(nm.split())>1 else "","items":{}}
                recs.append(rec); r=r[1:]
            if rec is None: continue
            if len(r)>=4: kind, amt, basis = r[1], r[2], r[3]
            elif len(r)==3: kind, amt, basis = r[0], r[1], r[2]
            elif len(r)==2: kind, amt, basis = r[0], r[1], ""
            else: continue
            kind=kind.replace(" ","")
            amt=amt.replace(",","").strip()
            rec["items"][kind]={"amt": int(amt) if amt.isdigit() else 0, "basis": basis}
        for rec in recs:
            # 보조 필드
            b=rec["items"].get("퇴직소득",{}).get("basis","")
            m=re.search(r"근무기간\s*(\d+)\s*년",b); rec["exec_years"]=int(m.group(1)) if m else None
            m=re.search(r"지급배수\s*\(?([\d.~]+)",b); rec["multiple"]=m.group(1) if m else None
            m=re.search(r"퇴직기준급여\s*([\d,]+)\s*백만원",b); rec["base_pay_mm"]=int(m.group(1).replace(",","")) if m else None
            g=rec["items"].get("급여",{}).get("basis","")
            m=re.search(r"직위\s*\(([^)]+)\)",g); rec["pay_grade"]=m.group(1) if m else ""
            rec["total"]=sum(v["amt"] for v in rec["items"].values())
            out.append(rec)
# 중복 제거(같은 표가 두 번 나옴: 이사·감사 개인별 + 5억 이상)
seen={}; 
for r in out: seen[(r["year"],r["name"])]=r
out=list(seen.values())
(D/"pay_detail.json").write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding="utf-8")
with open(D/"_paydetail.txt","w",encoding="utf-8") as f:
    for r in sorted(out,key=lambda r:(r["year"],-r["total"])):
        it=r["items"]; f.write(f"{r['year']} {r['name']:5} {r['ofcps']:10} 총{r['total']:>6} 급여{it.get('급여',{}).get('amt',0):>5} 상여{it.get('상여',{}).get('amt',0):>5} 퇴직{it.get('퇴직소득',{}).get('amt',0):>6} 기타{it.get('기타소득',{}).get('amt',0):>5} | 직위:{r['pay_grade']} 임원{r['exec_years']}년 배수{r['multiple']} 기준급{r['base_pay_mm']}\n")
print(len(out))
