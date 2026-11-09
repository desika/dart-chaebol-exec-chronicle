"""persons.json + exec_raw + pay_raw + pay_detail → data/app_data.json (앱 전용 통합 데이터)
   group_map.json(출신 그루핑 규칙, 사용자 편집)이 없으면 기본값 생성."""
import json, re, pathlib, collections, sqlite3
from company import CFG, D, SELF_PFX, GROUP_RX, GROUP_NAME, THIS_YEAR, NOW_DEC, TODAY
TM = CFG.get("title_merge_year")   # 전무→부사장 통합 인사 연도(없으면 구분 안 함)
from careerlib import split_edu_tail
CONAME = CFG["name"]
P = json.load(open(D/"persons.json", encoding="utf-8"))
RAW = json.load(open(D/"exec_raw.json", encoding="utf-8"))
PAY = json.load(open(D/"pay_raw.json", encoding="utf-8"))
PD = json.load(open(D/"pay_detail.json", encoding="utf-8"))
_i = lambda v: int(re.sub(r"[^\d-]", "", str(v or "")) or 0) if re.search(r"\d", str(v or "")) else 0   # 금액·인원 칸의 "-", "" 는 0

def norm(s): return re.sub(r"\s+", " ", (s or "")).strip()
def nm(s): return norm(s).replace(" ", "").replace("&cr;", "")
RC = {"11011": "사업", "11012": "반기", "11013": "1분기", "11014": "3분기"}

# ---------- 학교 정규화 / 지역 ----------
SCHOOL_ALIAS = {
    "서울대학교": "서울대", "고려대학교": "고려대", "연세대학교": "연세대", "성균관대학교": "성균관대", "성균관대학교대학원": "성균관대",
    "중앙대학": "중앙대", "한양대학교": "한양대", "서울시립대학교": "서울시립대", "와세다대학": "와세다대", "게이오대학": "게이오대",
    "일본대학": "니혼대", "도쿄대학교": "도쿄대", "소카대학교": "소카대", "New York University": "뉴욕대(NYU)", "NewYorkUniversity": "뉴욕대(NYU)", "New York Univ.": "뉴욕대(NYU)", "NYU": "뉴욕대(NYU)",
    "SUNY Stony Brook University": "스토니브룩대(SUNY)", "Columbia Univ.": "컬럼비아대", "Emory Univ.": "에모리대", "미국인디애나대학원": "인디애나대",
    "조지아대": "조지아대", "버지니아대": "버지니아대", "노스캐롤라이나대": "노스캐롤라이나대", "히토츠바시대학": "히토츠바시대", "츠쿠바대학": "츠쿠바대",
    "가쿠슈인대학": "가쿠슈인대", "메이지가쿠인대학": "메이지가쿠인대", "도쿄이과대학": "도쿄이과대", "장안실전": "장안전문대", "공사": "공군사관학교(추정)",
    "한국과학기술원": "KAIST", "금오공대": "금오공대", "동경대": "도쿄대", "동경대학": "도쿄대", "시라큐스대": "시러큐스대", "시라큐스대학교": "시러큐스대",
}
REGION = {
    "서울·수도권": ["서울대","고려대","연세대","성균관대","중앙대","한양대","서울시립대","서강대","홍익대","동국대","단국대","경희대","아주대","한밭대","장안전문대","KAIST","건국대","국민대","숭실대","광운대","명지대","인하대","한국외대","이화여대","세종대","가톨릭대"],
    "부산·울산·경남": ["부산대","경남대","동아대","경성대","김해고","창원대","울산대","부경대","동의대","인제대"],
    "대구·경북": ["경북대","영남대","금오공대","계명대","대구대","안동대"],
    "광주·전라": ["전남대","전북대","전라고","조선대","원광대","호남대","군산대"],
    "대전·충청": ["충북대","충남대","한밭대","공주대","순천향대","청주대","KAIST"],
    "강원": ["강원대","강릉대","강릉원주대"],
    "일본": ["와세다대","게이오대","니혼대","도쿄대","소카대","히토츠바시대","츠쿠바대","가쿠슈인대","메이지가쿠인대","도쿄이과대"],
    "미국·해외": ["뉴욕대(NYU)","스토니브룩대(SUNY)","컬럼비아대","에모리대","인디애나대","조지아대","버지니아대","노스캐롤라이나대","조지타운대"],
}
# 한밭대는 대전, KAIST는 대전으로
REGION["서울·수도권"] = [s for s in REGION["서울·수도권"] if s not in ("한밭대", "KAIST")]
R_OF = {s: r for r, ss in REGION.items() for s in ss}
EN_SCHOOL_RX = re.compile(r"Univ|University|Institute|Inst\.|College|School|Tech\.|MIT|Harvard|Stanford|Princeton|Berkeley|Carnegie|UCLA|Polytechnic|HEC|LSE|INSEAD|Sup de Pub|\((?:프랑스|미국|영국|독일|중국|캐나다|호주|이탈리아|스페인|스위스)\)|시카고대|시러큐스|조지아대|콜롬비아|컬럼비아", re.I)
def region_of(school):
    if not school: return ""
    if school in R_OF: return R_OF[school]
    if school.endswith("(일본)") or re.search(r"(와세다|게이오|도쿄|동경|교토|오사카|히토츠바시|조치)", school): return "일본"
    return "미국·해외" if EN_SCHOOL_RX.search(school) else "미상"
def en_canon(s):
    """영문 학교명 통일: University→Univ., Institute→Inst., Technology→Tech., 캠퍼스 꼬리(', Austin', ', Urbana-Champaign') 제거"""
    s = re.sub(r"\bUniversity\b", "Univ.", s); s = re.sub(r"\bUniv\b(?!\.)", "Univ.", s)
    s = re.sub(r"\bInstitute\b", "Inst.", s); s = re.sub(r"\bInst\b(?!\.)", "Inst.", s); s = re.sub(r"\bTechnology\b", "Tech.", s)
    s = re.sub(r",\s*[A-Za-z .\-]+$", "", s)   # 캠퍼스·도시 꼬리
    return re.sub(r"\s+", " ", s).strip(" ,")
def school_canon(s):
    s = norm(s).replace(" 대학원", "")
    if s.startswith("Sup de Pub"): return "Sup de Pub(프랑스)"
    if re.match(r"Helsinki (Sch|School)", s): return "Helsinki School of Economics"
    if re.search(r"[A-Za-z]", s) and not re.search(r"[가-힣]", s): s = en_canon(s)
    if s.endswith("대학원") and not s.endswith("대학원대학교"): s = s[:-3]
    if s.endswith("대학교") and len(s) > 3 and s[:-3].endswith("대학교"): s = s[:-3]   # '시라큐스대학교대학교' 류 정리
    if s in SCHOOL_ALIAS: return SCHOOL_ALIAS[s]
    s2 = re.sub(r"(대학교|대학)$", "대", s)
    return SCHOOL_ALIAS.get(s2, s2)

def edu_schools(detail, primary, final_degree="", grad_year=None):
    """학력상세('1994 졸업 건국대 / 1997 석사 동경대 / 2002 석사(MBA) 시카고대') → [{school, degree, year}]
       과정은 학사/석사/박사/MBA/전문학사/고졸/수료로 구분하고 같은 학교라도 과정이 다르면 따로 둔다(서울대 학사 ≠ 서울대 MBA)."""
    out = []
    def deg_of(d, sch):
        d = d or ""
        if "MBA" in d: return "MBA"
        if re.search(r"(고등학교|상고|공고|실업고|여고|[가-힣]고)$", sch): return "고졸"
        if re.search(r"(실전|전문대)$", sch): return "전문학사"
        return {"졸업": "학사", "학사": "학사", "석사": "석사", "박사": "박사", "수료": "수료", "중퇴": "중퇴"}.get(d, d or "학사")
    def add(sch, deg, year):
        c = school_canon(sch) if sch else ""
        if not c: return
        d = deg_of(deg, c)
        hit = next((o for o in out if o["school"] == c and o["degree"] == d), None)
        if hit is None: out.append({"school": c, "degree": d, "year": year})
        elif year and not hit["year"]: hit["year"] = year
    for part in (detail or "").split(" / "):
        m = re.match(r"^(\d{4})?\s*(졸업|수료|중퇴|학사|석사\(MBA\)|석사|박사|MBA)?\s*(.*)$", part.strip())
        if not m: continue
        year = int(m.group(1)) if m.group(1) else None; deg = m.group(2) or ""; sch = m.group(3).strip(" ,")
        if "MBA" in sch and deg in ("", "석사"): deg = "MBA"
        sch = re.sub(r"\s*(졸업|수료|학사|석사|박사|MBA)\s*$", "", sch).strip(" ,")
        if sch and not re.search(r"(팀장|부장|실장|담당|이사|상무|사장)", sch): add(sch, deg, year)
    if not out and primary: add(primary, {"고졸": "졸업", "전문학사": "졸업", "석사(MBA)": "MBA"}.get(final_degree, final_degree or "졸업"), grad_year)
    return out

# ---------- 출신 그루핑 규칙 (사용자 편집 파일) ----------
GM = D/"group_map.json"
if not GM.exists():
    GM.write_text(json.dumps({
        "_설명": "선임 당시/직전 보직 문자열을 '출신 그룹'으로 묶는 규칙. rules는 위에서부터 첫 매치. overrides는 이름별 강제 지정. 편집 후 build_data.py 재실행.",
        "rules": [
            {"match": "경영지원|경영관리|재무|경리|회계|자산|구매|총무", "group": "경영지원·재무"},
            {"match": "인사|HR|인재|노무|교육", "group": "인사"},
            {"match": "전략|기획|혁신|신사업|미래", "group": "전략·기획"},
            {"match": "감사|진단|준법|법무|컴플라이언스|변호사", "group": "감사·준법"},
            {"match": "커뮤니케이션|홍보|PR", "group": "커뮤니케이션"},
            {"match": "지원팀장|지원그룹장|지원실장|지원담당", "group": "사업부 지원(스태프)"},
            {"match": "R&D|연구|개발|솔루션|디바이스|알고리즘|영상|Lab", "group": "R&D·개발"},
            {"match": "엔지니어링|시공|기술|품질|TSC|정보보호|보안전략", "group": "기술·품질·엔지니어링"},
            {"match": "마케팅|상품", "group": "마케팅·상품"},
            {"match": "지사장|사업팀장|사업본부장|본부장|영업|B2B|부울|경남|경북|호남|강북|강남|서울|경기|경인|강원|서비스", "group": "지역·현장 영업"},
            {"match": "운영|안전|EHS|환경|PM사업|TS사업|부동산|FM", "group": "운영·안전·관리"},
        ],
        "overrides": {}
    }, ensure_ascii=False, indent=1), encoding="utf-8")
GMAP = json.loads(GM.read_text(encoding="utf-8"))
def group_of(name, *posts):
    if name in GMAP.get("overrides", {}): return GMAP["overrides"][name], "override"
    for post in posts:
        if not post: continue
        for r in GMAP["rules"]:
            if re.search(r["match"], post): return r["group"], post
    return "미분류", posts[0] if posts else ""

SECTOR_RULES = [tuple(x) for x in CFG["sector_rules"]] if CFG.get("sector_rules") else [
    ("시큐리티(SE/SP)", r"시큐리티|SE|SP|지역|지사|경남|경북|호남|강북|강남|서울사업|경기사업|경인|부울|강원사업|전략영업"),
    ("인프라(BE/TS/SI)", r"인프라|BE|TS|SI|건물|엔지니어링|부동산|PM사업|FM"),
    ("R&D·기술", r"R&D|연구|개발|솔루션|품질|정보보호|디바이스|기술"),
    ("전사 스태프", r"경영지원|인사|재무|전략|기획|커뮤니케이션|준법|감사|진단|EHS|안전|혁신|법무|경영진단"),
]
def sector_of(text):
    hits = collections.Counter()
    for sec, rx in SECTOR_RULES:
        hits[sec] += len(re.findall(rx, text or ""))
    best = hits.most_common(1)
    return best[0][0] if best and best[0][1] > 0 else "미상"

# ---------- 보수 ----------
pay_by = collections.defaultdict(list)   # name -> [{year, ofcps, total(억), src}]
for r in PAY["indvdlByPay"]:
    pay_by[nm(r["nm"])].append({"year": r["bsns_year"], "ofcps": norm(r["ofcps"]), "total": round(_i(r["mendng_totamt"]) / 1e8, 2), "src": "5억이상"})
for r in PAY["hmvAuditIndvdlBySttus"]:
    k = nm(r["nm"]); y = r["bsns_year"]
    if not any(p["year"] == y for p in pay_by[k]):
        pay_by[k].append({"year": y, "ofcps": norm(r["ofcps"]), "total": round(_i(r["mendng_totamt"]) / 1e8, 2), "src": "이사감사"})
detail_by = collections.defaultdict(dict)
for r in PD:
    if r["total"] <= 0: continue
    k = nm(r["name"]); it = r["items"]
    detail_by[k][r["year"]] = {
        "급여": it.get("급여", {}).get("amt", 0), "상여": it.get("상여", {}).get("amt", 0),
        "기타근로": it.get("기타근로소득", {}).get("amt", 0), "퇴직": it.get("퇴직소득", {}).get("amt", 0), "기타": it.get("기타소득", {}).get("amt", 0),
        "총액": r["total"], "임원근무년수": r["exec_years"], "지급배수": r["multiple"], "퇴직기준급여": r["base_pay_mm"],
        "급여산정": it.get("급여", {}).get("basis", ""), "상여산정": it.get("상여", {}).get("basis", ""), "퇴직산정": it.get("퇴직소득", {}).get("basis", ""), "직위표기": r["ofcps"]}
board_pay = [{"year": r["bsns_year"], "n": _i(r["nmpr"]), "total": round(_i(r["mendng_totamt"])/1e8, 1), "avg": round(_i(r["jan_avrg_mendng_am"])/1e8, 2)} for r in PAY["hmvAuditAllSttus"] if re.search(r"\d", str(r.get("mendng_totamt") or ""))]
emp = []
for r in PAY["empSttus"]:
    if "합계" in norm(r.get("fo_bbm", "")) or r["bsns_year"] <= 2021:
        try:
            emp.append({"year": r["bsns_year"], "div": norm(r["fo_bbm"]), "sex": norm(r["sexdstn"]), "n": _i(r["sm"]), "tenure": float(r["avrg_cnwk_sdytrn"] or 0), "avg_pay": round(_i(r["jan_salary_am"])/1e6) if re.search(r"\d", str(r["jan_salary_am"] or "")) else None})
        except ValueError: pass

# ---------- 인물 ----------
raw_by = collections.defaultdict(list)
for r in RAW: raw_by[(nm(r["nm"]), norm(r["birth_ym"]))].append(r)
ORDER = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}

def career_items(txt):
    t = re.sub(r"\s+", " ", (txt or "").replace("\n", " ")).strip()
    YR = r"(?:19|20)\d\d"
    if re.search(rf"{YR}\s*(?:[年년]|\.\s)", t):
        parts = re.split(rf"(?=(?:{YR})(?:\.\d{{1,2}})?(?:~\d{{4}}\.\d{{1,2}})?\s*(?:[年년]|\.\s))", t); out = []
        for p in parts:
            p = p.strip(); m = re.match(rf"({YR})", p)
            if m: out.append({"y": int(m.group(1)), "t": re.sub(rf"^{YR}(?:\.\d{{1,2}})?(?:~\d{{4}}\.\d{{1,2}})?\s*(?:[年년]|\.)\s*", "", p)})
        return out
    return [{"y": None, "t": p.strip(" -")} for p in re.split(r"\s*-\s+", t) if p.strip(" -")]
EDU = re.compile(r"(대학교|대학원|대학|대\b|Univ|University|College|MBA|학사|석사|박사|졸업|수료|고등학교|고교|고\b|실전\b|전문대|사관학교)", re.I)
NOTEDU = re.compile(r"(교수|강사|총장|사업부|팀장|그룹장|부장|이사|상무|대표|담당|실장|센터장|본부장|지사장|연구소장|위원|변호사|판사|차관|장관|회장|사장|파트장|고문|청장|국장|매니저|부사장|임원|소장|감사)")

people = []
for p in P:
    keys = [tuple(x) for x in p.get("원시키") or [[p["이름"], p["출생"]]]]   # analyze에서 병합된 출생월 오기·각주 표기 변형까지 모두
    rows = sorted([r for k in keys for r in raw_by[k]], key=lambda r: (r["bsns_year"], ORDER[r["reprt_code"]]))
    snaps = []
    for r in rows:
        snaps.append({"year": r["bsns_year"], "rc": RC[r["reprt_code"]], "ofcps": norm(r["ofcps"]).replace(" ", ""), "job": norm(r["chrg_job"]), "reg": norm(r["rgist_exctv_at"]),
                      "fte": norm(r["fte_at"]), "hffc": norm(r["hffc_pd"]), "tenure_end": norm(r["tenure_end_on"]), "career": norm(r["main_career"]).replace("年", "년"), "rcept": r["rcept_no"]})
    best = max(rows, key=lambda r: len(r["main_career"] or ""))
    items = career_items(best["main_career"])
    items = [{"y": y, "t": t} for y, t in split_edu_tail([(it["y"], it["t"]) for it in items])]
    for it in items: it["edu"] = bool(EDU.search(it["t"])) and not NOTEDU.search(it["t"])
    if items and not any(it["y"] for it in items):
        # 연도 없는 경력(한 줄형): 경력란 항목(선임 전) + 사업보고서 연도별 담당업무를 궤적으로 합성
        synth = []; prev_job = None
        for s in snaps:
            if s["rc"] != "사업" or not s["job"] or s["job"] == prev_job: continue
            synth.append({"y": s["year"], "t": s["job"], "edu": False, "src": "job"}); prev_job = s["job"]
        items = [dict(it, src="career") for it in items if it["edu"]] + [dict(it, src="career") for it in items if not it["edu"]] + synth
        items.sort(key=lambda it: (0 if it["edu"] else 1, it["y"] or 0))
    school = school_canon(p["학교"]) if p["학교"] else ""
    mba = bool(re.search(r"MBA", p["학력상세"] + " " + p["경력원문"]))
    # 보수는 이름으로만 공시되므로 동명이인 혼입 방지: 이 사람의 보고서 등장 구간(±1년) 안의 연도만
    fy, ly = p["첫등장"], snaps[-1]["year"]
    pays = sorted([x for x in pay_by.get(p["이름"], []) if fy - 1 <= x["year"] <= ly + 1], key=lambda x: x["year"])
    det = {y: d for y, d in detail_by.get(p["이름"], {}).items() if fy - 1 <= y <= ly + 1}
    sev_years = sorted(y for y, d in det.items() if d["퇴직"] > 0)
    # 퇴임 판정
    active = p["재직중"] == "Y"
    last_rep = snaps[-1]["year"]
    exit_year = None; exit_basis = ""
    exit_date = None if active else f"{last_rep + 1}-01-31"
    if sev_years:
        y0 = sev_years[0]
        if y0 == last_rep:   # 12/31 명단에 있으면서 그해 퇴직금 수령 → 그해 12월(연말 인사) 퇴임
            exit_date = f"{y0}-12-31"; exit_year = y0; exit_basis = f"{y0}년 보고서에 퇴직소득 공시 + 같은 해 명단에 있음 → {y0}년 12월 인사로 퇴임(그해 안에 퇴직금 수령)"
        else:                # 전년 명단에 있고 다음 해 퇴직금 → 전년 12월 인사, 1월 퇴직
            exit_date = f"{y0}-01-31"; exit_year = y0 - 1; exit_basis = f"{y0}년 보고서에 퇴직소득 공시 → {y0 - 1}년 12월 인사로 퇴임, {y0}년 1월 정식 종료"
    elif not active:
        exit_year = last_rep; exit_basis = f"{last_rep}년 사업보고서(12/31 기준)까지 등장 → {last_rep}년 12월 인사 퇴임으로 간주"
    appt = p["임원선임일"]
    ay = int(appt[:4]) if appt else None
    grp, grp_src = group_of(p["이름"], p["선임시보직"], p["선임전보직"], p["현담당"])
    if CFG.get("sector_from_job"):
        # 담당업무 접두어로 부문 판정('건설 ○○팀장'). 최근 사업보고서의 부문 우선, 없으면 최빈, 그래도 없으면 미상
        def _sec1(job):
            j = norm(job)
            return next((sec for sec, rx in SECTOR_RULES if re.search(rx, j)), None)
        _ann = [sn for sn in snaps if sn["rc"] == "사업"] or snaps
        _secs = [x for x in (_sec1(sn["job"]) for sn in _ann) if x]
        _last = _sec1(_ann[-1]["job"]) if _ann else None
        _div = [x for x in _secs if x != "전사·경영기획"]
        # 최근 담당이 전사형('대표이사 경영위원회 위원')이어도 이력에 부문이 있으면 그 부문(최빈)으로 본다
        sector = (_last if (_last and (_last != "전사·경영기획" or not _div)) else None) or (collections.Counter(_div or _secs).most_common(1)[0][0] if _secs else "미상")
    else: sector = sector_of(" ".join([p["담당변천"], p["경력원문"]]))
    if CFG.get("sector_from_job") and sector == "미상":   # 담당업무에 부문 접두어가 없으면(2016~17 "대표이사"만) 경력란에서 부문 단어를 찾는다
        sector = next((sec for sec, rx in SECTOR_RULES if sec != "전사·경영기획" and re.search(rx.replace("^", ""), p["경력원문"] or "")), "미상")
    sector = CFG.get("sector_overrides", {}).get(p["이름"], sector)
    titles = []  # 직위 구간: [{from, to, ofcps}] 보고서 연도 기준
    for s in snaps:
        if s["rc"] != "사업" and titles and titles[-1]["ofcps"] == s["ofcps"]: titles[-1]["to"] = s["year"]; continue
        if titles and titles[-1]["ofcps"] == s["ofcps"]: titles[-1]["to"] = s["year"]
        else: titles.append({"from": s["year"], "to": s["year"], "ofcps": s["ofcps"]})
    promos=[]; prev=None
    for sn in snaps:
        if sn["rc"]!="사업": continue
        if prev and prev["ofcps"]!=sn["ofcps"]:
            up = ("상무" in prev["ofcps"] and ("부사장" in sn["ofcps"] or "전무" in sn["ofcps"])) or ("전무" in prev["ofcps"] and "부사장" in sn["ofcps"]) or ("부사장" in prev["ofcps"] and re.search(r"(?<!부)사장", sn["ofcps"]))
            regime = ("통합후(전무 폐지)" if sn["year"] > TM else "통합전") if TM else ""
            note=""
            if "상무" in prev["ofcps"] and "부사장" in sn["ofcps"]:
                note = ("부사장 승진. 전무 통합 이후라 구 전무 승진에 해당할 수 있음" if sn["year"] > TM else "부사장 승진(전무 직급 존재 시기)") if TM else "부사장 승진"
            promos.append({"year": sn["year"], "hr_year": sn["year"]-1, "from": prev["ofcps"], "to": sn["ofcps"], "up": bool(up), "regime": regime, "note": note})
        prev=sn
    jm_trace = bool(re.search(r"전무", p["경력원문"]))
    jm_hits = [m.group(0) for m in re.finditer(r"[^ ]{0,12}전무[^ ]{0,6}", p["경력원문"])]
    people.append({
        "promos": promos, "jm_trace": jm_trace, "jm_hits": jm_hits,
        "id": f"{p['이름']}_{p['출생연도']}", "name": p["이름"], "sex": p["성별"], "birth": p["출생"], "birth_year": p["출생연도"], "grp": p["구분"],
        "reg": p["등기구분"], "title": p["현직위"], "job": p["현담당"], "appt": appt, "appt_year": ay, "appt_age": p["선임시나이"],
        "first_report": p["첫등장"], "appt_est": p.get("선임일추정") == "Y", "appt_src": p.get("선임일형식", ""), "last_report": last_rep, "active": active, "exit_year": exit_year, "exit_date": exit_date, "exit_basis": exit_basis,
        "exit_label": (exit_date[:7].replace("-", ".") if exit_date else ""),
        "tenure_years": (round((int(exit_date[:4]) + (int(exit_date[5:7]) - 1) / 12) - (int(appt[:4]) + (int(appt[5:7]) - 1) / 12), 1) if (exit_date and appt) else (round(NOW_DEC - (int(appt[:4]) + (int(appt[5:7]) - 1) / 12), 1) if appt else None)),
        "school_raw": p["학교"], "school": school, "schools": edu_schools(p["학력상세"], school, p["최종학위"], p["졸업연도"]), "region": region_of(school), "major": p["학과"], "grad_year": p["졸업연도"],
        "degree": p["최종학위"], "mba": mba, "edu_detail": p["학력상세"],
        "post_at_appt": p["선임시보직"], "post_before": p["선임전보직"], "origin_group": grp, "origin_src": grp_src, "sector": sector,
        "group_affil": p["그룹계열출신"] == "Y", "ext_career": p["외부경력"], "promotions": p["승진"], "title_hist": p["직위변천"], "job_hist": p["담당변천"],
        "snaps": snaps, "career": items, "titles": titles, "pay": pays, "pay_detail": {str(k): v for k, v in sorted(det.items())}, "severance_years": sev_years,
        "tenure_end": p["임기만료"], "career_text": p["경력원문"],
    })

# 트랙: 사장(그룹 파견) / 그룹 전입 임원 / 내부 성장 임원 / 세콤 파견 / 사외이사 / 감사
CEO_JOB = re.compile(r"^대표이사(?!\s*(보좌|비서|직속|부속|지원|담당|실|室))")   # "대표이사 보좌역"은 대표이사가 아니다
is_ceo_snap = lambda sn: bool(re.search(r"대표이사", re.sub(r"\s", "", sn["ofcps"])) or CEO_JOB.match(re.sub(r"\s", "", sn["job"])))
CC = json.load(open(D/"ceo_changes.json", encoding="utf-8")) if (D/"ceo_changes.json").exists() else []
CC_AFTER = {c["after"] for c in CC if c.get("after") and c.get("after") != c.get("before")}
for q in people:
    # 자사 대표이사 판정: 직위에 대표이사, 또는 담당업무가 '대표이사'로 시작(타사·자회사 대표이사 파견은 제외), 또는 대표이사 변경 공시의 변경 후 인물
    own_ceo = any(is_ceo_snap(sn) for sn in q["snaps"])
    is_ceo = (own_ceo or q["name"] in CC_AFTER) and not re.search(r"세콤", q["grp"])
    if q["grp"] != "경영진": q["track"] = q["grp"]
    elif is_ceo and q["group_affil"]: q["track"] = "사장(그룹 파견)"   # 그룹사 경력을 거쳐 사장으로 들어옴
    elif is_ceo: q["track"] = "사장(내부 승진)"   # 회사 안에서 임원을 거쳐 대표이사가 됨
    elif q["group_affil"]: q["track"] = "그룹 전입 임원"
    else: q["track"] = "내부 성장 임원"
    if q["name"] in GMAP.get("track_overrides", {}):
        q["track"] = GMAP["track_overrides"][q["name"]]; q["group_affil"] = (q["track"] != "내부 성장 임원") and q["group_affil"]

# 년차: 재직자는 올해 - 선임연도, 퇴임자는 퇴임 인사연도 - 선임연도 (12월 인사 기준, 최소 1)
for q in people:
    ay = q["appt_year"]
    if not ay: q["nth_year"] = None; continue
    end_y = THIS_YEAR if q["active"] else (q["exit_year"] or THIS_YEAR)
    q["nth_year"] = max(1, end_y - ay)

# 현 직위 년차: 마지막 '승진(up)'의 인사연도 기준. 승진 없으면 선임연도 기준. 퇴임자는 퇴임 인사연도까지
for q in people:
    ay = q["appt_year"]
    if not ay: q["grade_nth"] = None; q["grade_title"] = q["title"]; q["grade_from"] = None; continue
    ups = [pr for pr in q.get("promos", []) if pr.get("up")]
    first_known = next((sn["ofcps"] for sn in q["snaps"] if sn["rc"] == "사업"), q["title"])
    q["grade_min"] = False
    if ups: start = ups[-1]["hr_year"]
    elif q["track"] == "내부 성장 임원" and "상무" not in first_known and q["first_report"] > ay + 1:
        start = q["first_report"] - 1; q["grade_min"] = True   # 공시 전 승진: 늦어도 첫 공시 전년 12월 → '이상'
    else: start = ay
    end_y = THIS_YEAR if q["active"] else (q["exit_year"] or THIS_YEAR)
    q["grade_nth"] = max(1, end_y - start)
    q["grade_from"] = start
    q["grade_title"] = re.sub(r"\s", "", (ups[-1]["to"] if ups else q["title"]))

# 출신 그룹은 내부 성장 임원에게만 의미가 있음 (origin_group_override)
for q in people:
    if q["track"] in ("내부 성장 임원", "사장(내부 승진)"): continue
    ext_last = q["ext_career"].split(" / ")[-1] if q["ext_career"] else ""
    m = re.search("(" + CFG["group_companies_regex"] + ")", ext_last)
    comp = (m.group(1) if m else "").replace("삼성에스디에스", "삼성SDS").replace("SECOM", "세콤")
    post = ext_last.replace(comp, "").strip(" ,·") if comp else ext_last
    if q["track"] == "그룹 전입 임원": q["origin_group"] = f"{comp or '계열사'} 전입"; q["origin_note"] = f"계열사 전입 · {comp} {post} → {CONAME} {q['job_hist'].split(' → ')[0].split(':')[-1] if q['job_hist'] else ''}".strip()
    elif q["track"] == "사장(그룹 파견)": q["origin_group"] = f"{comp or '그룹'} → 사장"; q["origin_note"] = f"그룹 파견 · {comp} {post} → {CONAME} 사장"
    else: q["origin_group"] = q["track"]; q["origin_note"] = ext_last
    q["origin_src"] = ext_last

# 사장 취임 시점: 처음 '대표이사'로 공시된 사업보고서 연도 Y. 선임일이 Y(또는 Y-1 11월 이후)이면 선임일 그대로, 아니면 Y년 12월(정기인사)로 본다
for q in people:
    q["ceo_from"] = None
    if not q["track"].startswith("사장("): continue
    ys = [sn["year"] for sn in q["snaps"] if sn["rc"] == "사업" and is_ceo_snap(sn)]
    ysq = [sn["year"] for sn in q["snaps"] if is_ceo_snap(sn)]
    if not ys:
        # 사업보고서에는 아직 없고 분기·반기에만 대표이사: 그 전 해 사업보고서가 있으면 12월 인사 취임, 없으면 선임일
        ap = q["appt"] or ""; Yq = min(ysq) if ysq else None
        if Yq and ap and ((ap[:4] == str(Yq - 1) and int(ap[5:7]) >= 11) or (ap[:4] == str(Yq) and int(ap[5:7]) <= 3)): q["ceo_from"] = ap   # 선임일이 직전 11월~당해 3월이면 그대로
        elif Yq and any(sn["year"] < Yq for sn in q["snaps"] if sn["rc"] == "사업"): q["ceo_from"] = f"{Yq - 1}-12-01"; q["ceo_basis"] = f"{Yq}년 분기보고서부터 대표이사 → {Yq - 1}년 12월 인사로 간주"
        else: q["ceo_from"] = q["appt"]
        continue
    Y = min(ys); ap = q["appt"] or ""
    earlier_non_ceo = any(sn["year"] < Y for sn in q["snaps"] if sn["rc"] == "사업")   # 그 전에 대표이사가 아닌 채로 공시된 해가 있는가
    prev = [sn for sn in q["snaps"] if sn["rc"] == "사업" and sn["year"] == Y - 1]; prev2 = [sn for sn in q["snaps"] if sn["rc"] == "사업" and sn["year"] == Y - 2]
    new_pres = prev and re.sub(r"\s", "", prev[0]["ofcps"]) == "사장" and not (prev2 and re.search(r"사장", prev2[0]["ofcps"]) and not re.search(r"부사장", prev2[0]["ofcps"]))
    if ap and (ap[:4] == str(Y) or (ap[:4] == str(Y - 1) and int(ap[5:7]) >= 11)) and not (new_pres and ap[:4] == str(Y)): q["ceo_from"] = ap
    elif new_pres: q["ceo_from"] = f"{Y - 1}-12-01"; q["ceo_basis"] = f"{Y - 1}년 보고서에 신임 '사장'(부문장) → {Y - 1}년 12월 인사 취임, 이듬해 대표이사 등기로 간주"
    elif ap and ap[:4] == str(Y + 1) and int(ap[5:7]) <= 3 and q.get("appt_src") == "개월": q["ceo_from"] = f"{Y}-12-01"; q["ceo_basis"] = f"재직기간이 등기일({ap}) 기준 개월 역산이라 {Y}년 12월 인사로 간주"
    elif ap and ap[:4] > str(Y): q["ceo_from"] = ap
    elif earlier_non_ceo:
        # 분기보고서가 있으면 그 해 처음 대표이사로 나온 분기로 좁힌다(1분기→3월, 반기→6월, 3분기→9월). 없으면 12월 인사
        _qm = {"1분기": 3, "반기": 6, "3분기": 9}; _qs = sorted((_qm[sn["rc"]], sn["rc"]) for sn in q["snaps"] if sn["year"] == Y and sn["rc"] in _qm and is_ceo_snap(sn))
        _had_q = any(sn["year"] == Y and sn["rc"] in _qm for sn in q["snaps"])
        if _qs: q["ceo_from"] = f"{Y}-{_qs[0][0]:02d}-01"; q["ceo_basis"] = f"{Y}년 {_qs[0][1]}보고서부터 대표이사(연중 취임, 그 분기 말 기준)"
        elif _had_q: q["ceo_from"] = f"{Y}-12-01"; q["ceo_basis"] = f"{Y}년 분기보고서에는 없고 사업보고서부터 대표이사 → 12월 인사"
        else: q["ceo_from"] = f"{Y}-12-01"
    else: q["ceo_from"] = ap or f"{Y}-12-01"
    if q["ceo_from"] != ap:
        q["grade_from"] = Y; end_y = THIS_YEAR if q["active"] else (q["exit_year"] or THIS_YEAR); q["grade_nth"] = max(1, end_y - Y); q["grade_title"] = "사장"
# 대표이사 변경 수시공시(등기 기준일)로 보정: 재직기간 공시가 없어 선임일을 추정한 옛 사장만
for q in people:
    if not q["track"].startswith("사장(") or not q.get("appt_est"): continue
    hits = sorted(c["change_date"] or c["date"] for c in CC if c.get("after") == q["name"] and c.get("after") != c.get("before"))
    ys = [sn["year"] for sn in q["snaps"] if sn["rc"] == "사업" and (re.search(r"대표이사", re.sub(r"\s", "", sn["ofcps"])) or re.match(r"^대표이사", re.sub(r"\s", "", sn["job"])))]
    cand = [d for d in hits if ys and int(d[:4]) <= min(ys) + 1]
    if cand:
        # 등기 변경일이 처음 대표이사로 공시된 사업연도보다 뒤(이듬해 3월 주총)면 그해 12월 정기인사로 본다
        q["ceo_from"] = cand[0] if int(cand[0][:4]) <= min(ys) else f"{min(ys)}-12-01"
        q["ceo_basis"] = f"대표이사 변경 공시 {cand[0]}(등기 기준) · 재직기간 미공시라 선임일 대신 사용" + ("" if q["ceo_from"] == cand[0] else f" → {min(ys)}년 12월 인사로 간주")
        if q["appt"] > cand[0]: q["appt"] = cand[0]; q["appt_year"] = int(cand[0][:4])
# 대표이사 변경 수시공시가 있는 모든 사장에 일반 보정: 사업보고서의 '대표이사' 표기가 늦거나 빠진 회사('사장 · 경영전반 총괄' 식 표기)를 위해
_mi = lambda d: int(d[:4]) * 12 + int(d[5:7]) - 1
for q in people:
    if not q["track"].startswith("사장(") or not q.get("ceo_from"): continue
    hits = sorted(c["change_date"] or c["date"] for c in CC if c.get("after") == q["name"] and c.get("after") != c.get("before"))
    if not hits: continue
    d = hits[0]; near = lambda x: x and (-4 <= _mi(x) - _mi(d) <= 1)   # 등기일 4개월 전 ~ 1개월 후면 같은 취임으로 본다(12월 인사 → 3월 등기)
    ys_doc = [sn["year"] for sn in q["snaps"] if sn["rc"] == "사업" and is_ceo_snap(sn)]
    if ys_doc and min(ys_doc) < int(d[:4]) - 1: continue   # 공시 변경일보다 2년 이상 전부터 대표이사로 보고됨(공동대표의 대표 변경 등) → 보정 안 함
    if near(q["ceo_from"]): continue
    if near(q["appt"]): q["ceo_from"] = q["appt"]; q["ceo_basis"] = f"대표이사 변경 공시 {d}(등기) 직전 선임일 사용"
    else:
        prev_listed = any(sn["year"] == int(d[:4]) - 1 and sn["rc"] == "사업" and re.search(r"사장|대표", sn["ofcps"]) for sn in q["snaps"])
        q["ceo_from"] = f"{int(d[:4]) - 1}-12-01" if (int(d[5:7]) <= 3 and prev_listed) else d
        q["ceo_basis"] = f"대표이사 변경 공시 {d}(등기 기준)" + ("" if q["ceo_from"] == d else f" → {int(d[:4]) - 1}년 12월 인사로 간주")
    Y = int(q["ceo_from"][:4]); q["grade_from"] = Y; end_y = THIS_YEAR if q["active"] else (q["exit_year"] or THIS_YEAR); q["grade_nth"] = max(1, end_y - Y); q["grade_title"] = "사장"
# 사장 임기: 후임 사장 취임일 = 전임 사장 임기 종료(ceo_to). 후임 취임 뒤에도 임원으로 남은 경우(최규홍 2008 이사)는 개인 퇴임은 일반 규칙 유지
ceos = sorted([q for q in people if q["track"].startswith("사장(") and q.get("ceo_from")], key=lambda q: q["ceo_from"])
def _dec(d): return int(d[:4]) + (int(d[5:7]) - 1) / 12 + (int(d[8:10]) - 1) / 365
# 공동대표 체제 판정: 같은 사업보고서에 자사 대표이사가 2명 이상인 해가 3년 이상(부문별 대표 체제). 교체기 1~2년 겹침은 단일 사슬로 본다
_cy = {q["id"]: {sn["year"] for sn in q["snaps"] if sn["rc"] == "사업" and is_ceo_snap(sn)} for q in ceos}
_yc = collections.Counter(y for ys_ in _cy.values() for y in ys_)
# 교체기 1년 겹침(전임 12월 퇴임·후임 취임이 같은 보고서)은 단일 사슬. 한 해 3명 이상이거나 같은 두 사람이 2년 이상 함께 대표이사면 공동대표
CO_CEO = any(n >= 3 for n in _yc.values()) or any(len(_cy[a] & _cy[b]) >= 2 for i, a in enumerate(_cy) for b in list(_cy)[i + 1:])
for i, q in enumerate(ceos):
    if CO_CEO:
        ceo_years = [sn["year"] for sn in q["snaps"] if is_ceo_snap(sn)]; L = max(ceo_years) if ceo_years else None
        later_non = [sn for sn in q["snaps"] if L and sn["year"] > L and not is_ceo_snap(sn)]
        if L and later_non: q["ceo_to"] = f"{L}-12-01"; q["exit_basis"] = (q.get("exit_basis") or "") + f" · 공동대표 체제: 대표이사 임기는 {L}년 보고서까지({L}년 12월 인사 종료), 이후 다른 직책"
        elif q["active"]: q["ceo_to"] = None
        else: q["ceo_to"] = q["exit_date"]
        end = _dec(q["ceo_to"]) if q["ceo_to"] else NOW_DEC
        ten = max(0.0, end - _dec(q["ceo_from"])); q["ceo_tenure"] = round(ten, 1); q["ceo_nth"] = max(1, int(ten + 0.5))
        q["grade_title"] = "사장"; q["grade_from"] = int(q["ceo_from"][:4]); q["grade_nth"] = q["ceo_nth"]; q["grade_min"] = False
        continue
    nxt = ceos[i + 1]["ceo_from"] if i + 1 < len(ceos) else None
    q["ceo_to"] = nxt if (nxt and not q["active"]) else None
    if q["ceo_to"]:
        ny = int(nxt[:4])
        if q["last_report"] <= ny:   # 후임 취임 해 이후 보고서에 없음 → 사장 퇴임 = 임원 퇴임
            q["exit_date"] = nxt; q["exit_label"] = nxt[:7].replace("-", "."); q["exit_year"] = ny if int(nxt[5:7]) >= 11 else ny - 1
            q["exit_basis"] = f"후임 사장 {ceos[i + 1]['name']} 취임일({nxt})을 종료일로 사용"
        else:
            q["exit_basis"] = (q.get("exit_basis") or "") + f" · 사장 임기는 후임 {ceos[i + 1]['name']} 취임({nxt})까지, 이후 임원으로 재직"
    end = _dec(q["ceo_to"]) if q["ceo_to"] else (NOW_DEC if q["active"] else (_dec(q["exit_date"]) if q["exit_date"] else NOW_DEC))
    ten = max(0.0, end - _dec(q["ceo_from"]))
    q["ceo_tenure"] = round(ten, 1); q["ceo_nth"] = max(1, int(ten + 0.5))
    q["tenure_years"] = q["ceo_tenure"]
    q["grade_title"] = "사장"; q["grade_from"] = int(q["ceo_from"][:4]); q["grade_nth"] = q["ceo_nth"]; q["grade_min"] = False

# 전 직장 공시 흔적 (fetch_origins_docs.py 결과)
OD = json.load(open(D/"origin_docs.json", encoding="utf-8")) if (D/"origin_docs.json").exists() else []
OA = json.load(open(D/"origin_raw.json", encoding="utf-8")) if (D/"origin_raw.json").exists() else []
TITLE_RX = re.compile(r"^(회장|부회장|사장|부사장|전무|상무|대표이사|사내이사|감사)")
def trace_of(pid):
    rows = []
    for r in OD:
        if r["pid"] != pid: continue
        cs = [c.replace("&cr;", " ").strip() for c in r["cells"]]
        title = next((c for c in cs if TITLE_RX.match(c)), "")
        note = next((c for c in cs if re.search(r"의원면직|관계사 전출|임원사임|경력입사|선임|퇴임|사임", c) and len(c) < 12), "")
        school = next((c for c in cs if re.search(r"(대|Univ|University)", c) and len(c) < 20 and not TITLE_RX.match(c)), "")
        job = ""
        for c in cs:
            if c in (r["name"], title, note, school) or re.match(r"(19|20)\d\d", c) or c in ("남", "여", "상근", "비상근", "미등기임원", "미등기 임원", "등기임원", "미등기", "해당없음", "해당사항없음", "-", ""): continue
            if re.search(r"(팀장|실장|담당|총괄|사업부|부문|본부|그룹장|센터장|사장)", c): job = c; break
        rows.append({"company": r["company"], "year": r["year"], "title": title, "job": job, "note": note, "school": school, "raw": " · ".join(c for c in cs if c)})
    for r in OA:
        if r["pid"] != pid: continue
        if any(x["company"] == r["company"] and x["year"] == r["year"] for x in rows): continue
        rows.append({"company": r["company"], "year": r["year"], "title": r["ofcps"], "job": r["chrg_job"], "note": "", "school": "", "raw": f"{r['ofcps']} · {r['chrg_job']} · {r['main_career'][:120]}"})
    rows.sort(key=lambda x: (x["year"], x["company"]))
    # 구간: 회사별 연속 연도
    segs = []
    for x in rows:
        if x["note"] and re.search(r"면직|사임|퇴임|전출", x["note"]) and not x["title"]: continue
        if segs and segs[-1]["company"] == x["company"] and segs[-1]["to"] == x["year"]: segs[-1]["to"] = x["year"] + 1; segs[-1]["title"] = x["title"] or segs[-1]["title"]
        elif segs and segs[-1]["company"] == x["company"] and segs[-1]["to"] == x["year"] + 1: pass
        else: segs.append({"company": x["company"], "from": x["year"], "to": x["year"] + 1, "title": x["title"]})
    return rows, segs
for q in people:
    q["pre_trace"], q["pre_segs"] = trace_of(q["id"])
ORIGIN_SCAN = CFG["origin_scan"]

# 명단 외 보수 공시 인물
listed = {q["name"] for q in people}
extra_pay = []
for k, v in pay_by.items():
    if k not in listed:
        extra_pay.append({"name": k, "pay": sorted(v, key=lambda x: x["year"]), "pay_detail": {str(y): d for y, d in sorted(detail_by.get(k, {}).items())}})

# 관계망 엣지
edges = []
mg = [q for q in people if q["grp"] in ("경영진",)]
for i, a in enumerate(people):
    for b in people[i+1:]:
        # 동문 = 같은 학교 + 같은 과정(학사끼리·석사끼리·MBA끼리). 고졸은 잇지 않는다. 졸업연도 차이가 과정 길이 안이면 '같이 다녔을 듯'(same_time)
        SPAN = {"학사": 3, "전문학사": 1, "석사": 1, "MBA": 1, "박사": 3, "수료": 1, "중퇴": 3}
        for oa in a["schools"]:
            for ob in b["schools"]:
                if oa["school"] != ob["school"] or oa["degree"] != ob["degree"] or oa["degree"] == "고졸": continue
                same = bool(oa["year"] and ob["year"] and abs(oa["year"] - ob["year"]) <= SPAN.get(oa["degree"], 2))
                edges.append({"a": a["id"], "b": b["id"], "type": "동문", "label": f"{oa['school']} {oa['degree']}", "school": oa["school"], "degree": oa["degree"], "same_time": same, "years": [oa["year"], ob["year"]]})
        if a["group_affil"] and b["group_affil"]:
            edges.append({"a": a["id"], "b": b["id"], "type": "그룹계열", "label": f"{GROUP_NAME or '그룹'} 계열사 출신"})
# 보직 계승: 같은 보직명을 다른 해에 거친 사람
post_hold = collections.defaultdict(list)
for q in people:
    for it in q["career"]:
        if it["edu"] or not it["y"]: continue
        post = re.sub(SELF_PFX, "", it["t"]).strip()
        if re.search(r"(팀장|센터장|본부장|사업부장|그룹장|지사장|실장)$", post) and not re.search(GROUP_RX, post) and "세콤" not in post:
            post_hold[post].append((it["y"], q["id"]))
for post, lst in post_hold.items():
    lst = sorted(set(lst))
    ids = []
    for y, pid in lst:
        if pid not in ids: ids.append(pid)
    for i in range(len(ids)-1):
        edges.append({"a": ids[i], "b": ids[i+1], "type": "보직계승", "label": post})

# 이벤트
jm = sorted({(r["bsns_year"], nm(r["nm"])) for r in RAW if "전무" in (r["ofcps"] or "")})
events = []
if jm:
    events.append({"year": jm[-1][0], "label": f"마지막 '전무' 공시 ({jm[-1][1]}, {jm[-1][0]}년 사업보고서). {jm[-1][0]+1}년 보고서부터 전무 없음", "kind": "title"})
doc_years = sorted({r["bsns_year"] for r in RAW if r.get("src") == "doc"})
if doc_years: events.append({"year": doc_years[0], "label": f"사업보고서 원문 임원현황 표 파싱 범위 {doc_years[0]}~{doc_years[-1]} 사업연도(미등기임원 포함). 구조화 API는 2014년부터, 미등기는 회사에 따라 2021년부터만 제공", "kind": "data"})
events += CFG.get("events", [])

# 연도별 헤드카운트(사업보고서)
hc = collections.defaultdict(collections.Counter)
for r in RAW:
    if r["reprt_code"] == "11011": hc[r["bsns_year"]][norm(r["ofcps"]).replace(" ", "")] += 1

app = {"generated": TODAY.isoformat(), "company": {"name": CFG["name"], "corp_code": CFG["corp_code"], "stock": CFG["stock"], "group_name": GROUP_NAME, "title_merge_year": TM, "years": CFG["years"], "first_doc": CFG.get("first_doc", ""), "affiliate_hint": CFG.get("affiliate_hint", []), "has_affil": bool(CFG.get("affiliates")), "co_ceo": CO_CEO, "sector_label": CFG.get("sector_label", "사업부(추정)"), "sector_scope": bool(CFG.get("sector_scope")), "sector_default": CFG.get("sector_default", "")},
       "people": people, "edges": edges, "events": events, "board_pay": board_pay, "emp": emp, "extra_pay": extra_pay,
       "headcount": {y: dict(c) for y, c in sorted(hc.items())}, "group_rules": GMAP["rules"], "origin_scan": ORIGIN_SCAN,
       "regions": list(REGION.keys())}
(D/"app_data.json").write_text(json.dumps(app, ensure_ascii=False), encoding="utf-8")
unc = [q["name"] + ":" + (q["post_at_appt"] or q["job"]) for q in people if q["origin_group"] == "미분류" and q["grp"] == "경영진"]
print("people", len(people), "edges", len(edges), "extra_pay", len(extra_pay), "미분류", unc)
