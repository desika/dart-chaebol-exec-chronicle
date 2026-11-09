"""exec_raw → person 마스터. 사업보고서(연도별 상세, 年 표기)와 반기보고서(- 목록) 두 형식 모두 파싱."""
import sqlite3, re, json, collections, pathlib, csv
from company import CFG, D, DB, SELF_RX, SELF_PFX, GROUP_RX, THIS_YEAR
# 외부(타사·관청·학계) 경력 판정 힌트: 그룹 계열사 표기 + 범용 어휘(+설정 ext_hint_regex)
EXT_RX = re.compile(rf"(?:{GROUP_RX})|(?:{CFG.get('ext_hint_regex') or '은행|증권|보험|카드|캐피탈|자산운용|JP모건|S-Oil|포스코|경찰청|법원|검찰|국세청|사무소|회계법인|법무법인|대학|Univ|KDI|연구원|자원부|경제부|재정부|산업부|기획원|공사|공단'})")
con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute("select * from exec_raw")]
ORDER = {"11013":1,"11012":2,"11014":3,"11011":4}
def rk(r): return (r["bsns_year"], ORDER[r["reprt_code"]])
def norm(s): return re.sub(r"\s+", " ", (s or "")).strip()
def clean_nm(s): return re.sub(r"\(\*+\)|\*+|\(주\s*\d*\)|\(註\s*\d*\)|\[.*?\]", "", norm(s)).replace(" ","")   # 각주 표식 "유정근(*)" 제거
def pkey(r): return (clean_nm(r["nm"]), norm(r["birth_ym"]))
YR = r"(?:19|20)\d\d"
def career_items(txt):
    """[(연도 or None, 문장)] — 年/년 형식은 연도 단위, '- ' 형식은 항목 단위"""
    t = re.sub(r"\s+"," ",(txt or "").replace("\n"," ")).strip()
    if re.search(rf"{YR}\s*(?:[年년]|\.\s|\.\d{{1,2}}月)", t):
        parts = re.split(rf"(?=(?:{YR})(?:\.\d{{1,2}})?(?:~\d{{4}}\.\d{{1,2}})?\s*(?:[年년月]|\.\s))", t)
        out=[]
        for p in parts:
            p=p.strip(); m=re.match(rf"({YR})",p)
            if m: out.append((int(m.group(1)), re.sub(rf"^{YR}(?:\.\d{{1,2}})?(?:~\d{{4}}\.\d{{1,2}})?\s*(?:[年년月]|\.)\s*","",p)))
        return out
    # 항목 구분 대시: 뒤에 공백이 있거나(- A), 앞에 공백/문장 시작이 있으면(" -A", "-A") 분리. 단어 안 대시(S-1, e-Business, 2010-01)는 유지
    return [(None, p.strip(" -")) for p in re.split(r"\s*-\s+|(?:^|(?<=\s))-(?=\S)", t) if p.strip(" -")]
EDU_HINT = re.compile(r"(대학교|대학원|대학|대\b|Univ|University|College|MBA|학사|석사|박사|졸업|수료|고등학교|고교|고\b|실전\b|전문대)", re.I)
NOT_EDU = re.compile(r"(교수|강사|총장|사업부|팀장|그룹장|부장|이사|상무|대표|담당|실장|센터장|본부장|지사장|연구소장|위원|변호사|판사|차관|장관|회장|사장|파트장|고문|청장|국장|매니저|부사장|임원|소장|감사)")
def is_edu(p): return bool(EDU_HINT.search(p)) and not NOT_EDU.search(p)
def parse_school(e):
    s,mj,_=parse_edu(e)
    if s: return s, mj
    e=re.sub(r"^\d{4}\s*[年년]?\s*","",e)
    m=re.match(r"((?:[A-Za-z.]+\s)*?[A-Za-z.]*(?:Univ\.?|University|College|Institute(?:\sof\sTechnology)?|Inst\.(?:\sof\sTech\.?)?|Business School|School|Tech\.|MIT|KAIST|Polytechnic)[A-Za-z.\s]*?(?=\s[가-힣]|$)|[가-힣A-Za-z]+?(?:대학교|대학원대학교|대학원|대학|대|고등학교|고교|고|실전|공사|사관학교|과학기술원|학교)(?:\s*대학원)?)\s*(.*)$", e)
    if not m: return e, ""
    school=m.group(1).strip(); rest=m.group(2).strip()
    rest=re.sub(r"\s*(졸업|수료|학사|석사|박사|MBA)\s*(졸업|수료)?\s*$","",rest).strip()
    return school, rest
def degree_of(e):
    for d in ["MBA","박사","석사","학사","졸업","수료"]:   # MBA를 먼저 봐야 'Emory Univ. MBA 석사'가 MBA로 남는다
        if d in e: return "석사(MBA)" if d=="MBA" else d
    return ""
from careerlib import split_edu_tail, split_edu_head, parse_edu
def months_start(hp, ref):
    """'37개월' + 기준일(YYYY-MM-DD) → 시작 연월(포함 계산: 37개월이면 기준월 포함 37개월 전)"""
    m = re.search(r"(?:(\d+)\s*년)?\s*(\d+)\s*개월", hp or "")
    if not (m and ref and re.match(r"\d{4}-\d{2}", ref)): return None
    n = int(m.group(1) or 0) * 12 + int(m.group(2)); idx = int(ref[:4]) * 12 + int(ref[5:7]) - 1 - (n - 1)
    return f"{idx // 12}-{idx % 12 + 1:02d}-01"
def parse_start(hp, ref=None):
    hp = hp or ""
    if "개월" in hp and not re.search(r"(19|20)\d\d", hp): return months_start(hp, ref)
    m=re.search(rf"({YR})[.\-/]+(\d{{1,2}})(?:[.\-/]+(\d{{1,2}}))?", hp)
    if m: return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3) or 1):02d}"
    m=re.search(r"'(\d\d)[.\-/]+(\d{1,2})(?:[.\-/]+(\d{1,2}))?", hp)   # '11.12.07 형식
    if m: yy=int(m.group(1)); return f"{1900+yy if yy>30 else 2000+yy}-{int(m.group(2)):02d}-{int(m.group(3) or 1):02d}"
    return None

LATEST = max((r["bsns_year"], ORDER[r["reprt_code"]]) for r in rows)   # 데이터에 있는 가장 최근 보고서 = 현직 기준
persons=collections.OrderedDict()
for r in sorted(rows,key=rk):
    k=pkey(r)
    p=persons.setdefault(k,{"nm":k[0],"birth_ym":k[1],"sex":norm(r["sexdstn"]),"rows":[],"keys":{(norm(r["nm"]).replace(" ",""), norm(r["birth_ym"]))}})
    p["keys"].add((norm(r["nm"]).replace(" ",""), norm(r["birth_ym"])))
    p["rows"].append(r)

# 출생월이 보고서마다 다르게 적힌 동일 인물 병합: 이름 같고 출생연도 같고 등장 연도가 겹치지 않으면 하나로
by_nm=collections.defaultdict(list)
for k in list(persons): by_nm[k[0]].append(k)
for nm_, ks in by_nm.items():
    if len(ks) < 2: continue
    ks = sorted(ks, key=lambda k: -len(persons[k]["rows"]))
    merged = set()
    for i, main in enumerate(ks):
        if main in merged: continue
        for k in ks[i+1:]:
            if k in merged: continue
            same_year = (main[1][:4] == k[1][:4]) or not main[1] or not k[1]   # 출생연도 같거나 한쪽이 미기재
            ra = {(r["bsns_year"], r["reprt_code"]) for r in persons[main]["rows"]}; rb = {(r["bsns_year"], r["reprt_code"]) for r in persons[k]["rows"]}
            frag = all(r["reprt_code"] != "11011" for r in persons[k]["rows"]) and len(persons[k]["rows"]) <= 3   # 분기보고서에만 1~3번 나온 조각(출생연월 오기)
            if ra & rb: continue                       # 같은 보고서에 둘 다 있으면 다른 사람
            if not same_year and not frag: continue
            persons[main]["rows"] = sorted(persons[main]["rows"] + persons[k]["rows"], key=rk); persons[main]["keys"] |= persons[k]["keys"]
            if not persons[main]["birth_ym"] and k[1]: persons[main]["birth_ym"] = k[1]
            del persons[k]; merged.add(k); print(f"병합: {nm_} {k[1] or '(미기재)'} → {main[1] or '(미기재)'}")
out=[]
for k,p in persons.items():
    rs=p["rows"]; last=rs[-1]
    best=max(rs,key=lambda r: len(r["main_career"] or ""))
    items=split_edu_head(split_edu_tail(career_items(best["main_career"])))
    noyear=bool(items) and not any(i[0] for i in items)
    edu=[e for e in items if is_edu(e[1])]; car=[c for c in items if not is_edu(c[1])]
    starts=[s for s in (parse_start(r["hffc_pd"], r["stlm_dt"]) for r in rs) if s]
    appt_src = "개월" if any(("개월" in (r["hffc_pd"] or "") and not re.search(r"(19|20)\d\d", r["hffc_pd"] or "")) for r in rs) else "날짜"   # 개월 역산이면 등기일 기준이라 12월 인사와 어긋날 수 있음
    appt_est = False
    if not starts:
        fy = min(r["bsns_year"] for r in rs); appt = f"{fy}-12-31"; appt_est = True   # 재직기간 공시 없음 → 첫 등장 연도 말(늦어도 이 시점)
    else: appt=min(starts)
    appt_year=int(appt[:4]) if appt else None
    by=re.match(r"(\d{4})",p["birth_ym"]); birth_year=int(by.group(1)) if by else None
    age=(appt_year-birth_year) if (appt_year and birth_year) else None
    school=major=""; grad=None; degrees=[]
    if edu:
        grad,first=edu[0]; school,major=parse_school(first)
        for y,e in edu: degrees.append(f"{y or ''} {degree_of(e)} {parse_school(e)[0]}".strip())
    top_deg = "박사" if any("박사" in d for d in degrees) else "석사" if any("석사" in d for d in degrees) else ("학사" if edu else "")
    if top_deg=="학사" and re.search(r"(고등학교|고교|고)$",school): top_deg="고졸"
    elif top_deg=="학사" and re.search(r"(실전|전문대)$",school): top_deg="전문학사"
    major=re.sub(r"\s*\d{4}.*$","",major).strip()
    # 선임 직전 보직
    if appt_year and any(c[0] for c in car):
        pre=[c for c in car if c[0] and c[0]<=appt_year]
        pre_post=pre[-1][1] if pre else ""
    elif noyear and appt_year and next((r for r in rs if r["reprt_code"]=="11011"), rs[0])["bsns_year"] <= appt_year+1:
        # 연도 없는 경력(한 줄형, "-A -B" 목록형)이고 첫 사업보고서가 선임 직후일 때: 경력란 = 선임 전 보직, 선임 시 보직 = 첫 사업보고서 담당업무
        first_ann = next((r for r in rs if r["reprt_code"]=="11011"), rs[0]); pre_post = norm(first_ann["chrg_job"])
    else:
        # '- ' 목록 형식: 마지막 항목이 현 보직, 그 앞이 직전
        pre_post = car[-2][1] if len(car)>=2 else (car[0][1] if car else "")
    pre_post=re.sub(SELF_PFX,"",pre_post)
    # 선임 전년 이전의 마지막 보직(연도형식일 때만)
    prior=""
    if noyear:
        # 목록 형식은 '첫 사업보고서'의 경력란 마지막 항목이 선임 직전 보직(나중 보고서 목록에는 선임 후 보직이 섞인다)
        fa = next((r for r in rs if r["reprt_code"]=="11011"), rs[0])
        car_first = [c for c in split_edu_head(split_edu_tail(career_items(fa["main_career"]))) if not is_edu(c[1])]
        prior = re.sub(SELF_PFX,"",car_first[-1][1]) if car_first else (re.sub(SELF_PFX,"",car[-1][1]) if (car and fa["bsns_year"] > (appt_year or 0)+1) else "")
    elif appt_year and any(c[0] for c in car):
        pr=[c for c in car if c[0] and c[0]<appt_year]
        prior=re.sub(SELF_PFX,"",pr[-1][1]) if pr else ""
    # 외부 경력: 자사 표기가 섞인 한 줄("A사 대표이사 B사 대표이사")은 자사 구절(회사명+다음 어절)만 지우고 본다. 첫 보고서 경력란도 함께 본다
    strip_self = lambda s: re.sub(rf"(?:{SELF_RX})\S*(?:\s+\S+)?", " ", s)
    _fa = next((r for r in rs if r["reprt_code"]=="11011"), rs[0]); _car_first = [c for c in split_edu_head(split_edu_tail(career_items(_fa["main_career"]))) if not is_edu(c[1])]
    _seen = set(); _cands = [c[1] for c in car + _car_first if not (c[1] in _seen or _seen.add(c[1]))]
    ext=[c for c in _cands if EXT_RX.search(strip_self(c)) and not re.fullmatch(r"\s*", strip_self(c))]
    samsung_ext = "Y" if any(re.search(GROUP_RX, strip_self(e)) for e in ext) else "N"
    _ma = max([r["bsns_year"] for r in rs if r["reprt_code"]=="11011"] or [0]); _hs = [r for r in rs if r["reprt_code"]=="11011" or r["bsns_year"] > _ma]   # 과거 분기 행은 변천 표기에서 제외
    ofc_hist=list(dict.fromkeys(f"{r['bsns_year']}:{norm(r['ofcps']).replace(' ','')}" for r in _hs))
    job_hist=list(dict.fromkeys(f"{r['bsns_year']}:{norm(r['chrg_job'])}" for r in _hs))
    first_year=rs[0]["bsns_year"]; last_rep=(last["bsns_year"],last["reprt_code"])
    active = (last_rep[0], ORDER[last_rep[1]]) == LATEST
    reg=norm(last["rgist_exctv_at"]); ofc=norm(last["ofcps"]).replace(" ","")
    if reg in("독립이사","사외이사") or "사외" in ofc or "독립" in norm(last["chrg_job"]): grp="사외이사"
    elif "감사" in ofc: grp="감사"
    elif "기타비상무" in reg or "기타비상무" in ofc or "기타비상무" in norm(last["chrg_job"]): grp="세콤파견(비상무)" if CFG.get("secom") else "기타비상무이사"
    elif CFG.get("secom") and re.search(r"[가-힣]{2,}(히로|시|오|로|타|키|끼|스|지|이치|노리|루|코|미치|슈|시마|카즈|다|야|헤이|스케|로우|오사|다카|유키|카|노부|시게|이치로|지로|타로|히코|부로|마사|히데|아키|토시|츠|쯔|에|키요|요시)$",p["nm"]) and ("세콤" in (best["main_career"] or "") or "SECOM" in (best["main_career"] or "") or "비상근" in (norm(last["fte_at"])+ofc)):
        grp = "세콤파견(비상무)" if ("비상근" in (norm(last["fte_at"])+ofc) and "감사" not in ofc) else "세콤파견(사내)"
    else: grp="경영진"
    # 승진 이력: 직위가 바뀐 연도
    promo=[]
    prev=None
    for r in _hs:
        o=norm(r["ofcps"]).replace(" ","")
        if prev and o!=prev: promo.append(f"{r['bsns_year']} {prev}→{o}")
        prev=o
    out.append(dict(
        이름=p["nm"], 성별=p["sex"], 출생=p["birth_ym"], 출생연도=birth_year, 구분=grp, 원시키=sorted(list(x) for x in p["keys"]),
        등기구분=reg, 현직위=ofc, 현담당=norm(last["chrg_job"]),
        임원선임일=appt, 선임연도=appt_year, 선임시나이=age, 선임일추정="Y" if appt_est else "N", 선임일형식=("추정" if appt_est else appt_src),
        첫등장=first_year, 마지막보고서=f"{last_rep[0]} {'사업' if last_rep[1]=='11011' else '반기' if last_rep[1]=='11012' else '1분기'}",
        재직중="Y" if active else "N",
        퇴임추정연도=None if active else last_rep[0]+1,
        재임년수=( (THIS_YEAR if active else last_rep[0]+1) - appt_year) if appt_year else None,
        학교=school, 학과=major, 졸업연도=grad, 최종학위=top_deg, 학력상세=" / ".join(degrees),
        선임시보직=pre_post, 선임전보직=prior, 그룹계열출신=samsung_ext, 외부경력=" / ".join(ext),
        직위변천=" → ".join(ofc_hist), 담당변천=" → ".join(job_hist), 승진=" / ".join(promo),
        임기만료=norm(last["tenure_end_on"]), 경력원문=norm(best["main_career"]).replace("年","년"),
    ))
(D/"persons.json").write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding="utf-8")
cols=list(out[0].keys())
con.execute("drop table if exists person"); con.execute(f"create table person ({','.join(cols)})")
con.executemany(f"insert into person values ({','.join('?'*len(cols))})",[[json.dumps(o[c],ensure_ascii=False) if isinstance(o[c],(list,dict)) else o[c] for c in cols] for o in out]); con.commit()   # 원시키(list)는 JSON 문자열로
with open(D/"persons.csv","w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(out)
with open(D/"_preview.txt","w",encoding="utf-8") as f:
    for o in out:
        f.write(f"{o['이름']}|{o['구분']}|{o['출생연도']}|{o['현직위']}|{o['현담당'][:14]}|선임{o['임원선임일']}({o['선임시나이']})|{o['첫등장']}~{o['마지막보고서']} {o['재직중']}|{o['학교']}·{o['학과']}·{o['졸업연도']}·{o['최종학위']}|선임시:{o['선임시보직'][:20]}|전:{o['선임전보직'][:20]}|그룹{o['그룹계열출신']}|외부:{o['외부경력'][:40]}\n")
print(len(out))
