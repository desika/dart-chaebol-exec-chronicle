"""보수 관련 DART API 수집 → data/pay_raw.json
 indvdlByPay: 개인별 보수지급금액(5억 이상 상위 5명)  hmvAuditIndvdlBySttus: 이사·감사 개인별 보수
 hmvAuditAllSttus: 이사·감사 전체 보수  unrstrctdExctvMendngSttus: 미등기임원 보수  empSttus: 직원현황(규모 참고)"""
import json, time, urllib.request, urllib.parse, pathlib
from company import CFG, D, KEY, need_key
need_key()
CORP=CFG["corp_code"]; BASE="https://opendart.fss.or.kr/api/"
APIS=["indvdlByPay","hmvAuditIndvdlBySttus","hmvAuditAllSttus","unrstrctdExctvMendngSttus","empSttus"]
out={}
for api in APIS:
    out[api]=[]
    for y in range(CFG["years"]["pay_first"], CFG["years"]["last"]+1):
        q=urllib.parse.urlencode(dict(crtfc_key=KEY,corp_code=CORP,bsns_year=y,reprt_code="11011"))
        try:
            d=json.loads(urllib.request.urlopen(f"{BASE}{api}.json?{q}",timeout=30).read().decode("utf-8"))
        except Exception as e:
            print(api,y,"ERR",e); continue
        lst=d.get("list",[])
        for r in lst: r["bsns_year"]=y
        out[api]+=lst
        print(api,y,d.get("status"),len(lst))
        time.sleep(0.25)
(D/"pay_raw.json").write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding="utf-8")
