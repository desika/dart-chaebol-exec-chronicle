"""회사명 한 줄로 임원 도감 만들기.
   python add_company.py <회사명|corp_code> [--slug 영문] [--group 삼성|LG|SK|현대|롯데|한화|CJ|none] [--self 전신명] [--logo 파일] [--first 2016] [--no-fetch]
   DART 인증키: 환경변수 DART_API_KEY (또는 dart_key.txt)
   1) DART corpCode에서 회사 코드 조회  2) companies/<slug>/config.json + group_map.json(범용 규칙) 생성
   3) 파이프라인 실행(수집→파싱→분석→빌드→렌더)  4) 요약 + 렌더 검사
   만든 뒤 할 일: group_map.json을 그 회사 조직 어휘로 교정, 로고 넣기, 미분류 확인."""
import sys, re, json, pathlib, argparse, subprocess, os, time, zipfile, io, urllib.request, datetime, html
ROOT = pathlib.Path(__file__).resolve().parent
from dart_key import KEY, need_key
need_key()
ap = argparse.ArgumentParser(); ap.add_argument("name"); ap.add_argument("--slug"); ap.add_argument("--group"); ap.add_argument("--logo"); ap.add_argument("--first", type=int, default=2016, help="첫 사업연도(기본 2016: 최근 10년)"); ap.add_argument("--self", dest="self_extra", default="", help="자사 전신·별칭 정규식 대안(예: 제일모직|삼성에버랜드). 그룹 계열사 목록에서 제외된다"); ap.add_argument("--no-fetch", action="store_true")
A = ap.parse_args()

# ---- 1) 회사 코드
cc = ROOT/"companies"/"_corpcode.xml"
if not cc.exists() or (time.time() - cc.stat().st_mtime) > 30 * 86400:
    b = urllib.request.urlopen("https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key=" + KEY, timeout=180).read()
    cc.write_bytes(zipfile.ZipFile(io.BytesIO(b)).read("CORPCODE.xml"))
x = cc.read_text(encoding="utf-8")
ents = [dict(code=m.group(1), name=html.unescape(m.group(2)), eng=html.unescape(m.group(3)), stock=m.group(4).strip()) for m in re.finditer(r"<corp_code>(\d+)</corp_code>\s*<corp_name>([^<]*)</corp_name>\s*<corp_eng_name>([^<]*)</corp_eng_name>\s*<stock_code>([^<]*)</stock_code>", x)]
key = A.name.replace(" ", "")
if re.fullmatch(r"\d{8}", key): cands = [e for e in ents if e["code"] == key]
else:
    cands = [e for e in ents if e["name"].replace(" ", "") == key] or [e for e in ents if e["name"].replace(" ", "").startswith(key)]
cands.sort(key=lambda e: (not e["stock"], len(e["name"])))
if not cands: sys.exit(f"DART에 '{A.name}' 없음")
if len(cands) > 1: print("후보:", [(e["name"], e["code"], e["stock"] or "비상장") for e in cands[:8]], "→ 첫 번째 사용")
co = cands[0]; print("회사:", co)
name = co["name"]
slug = A.slug or (re.sub(r"[^a-z0-9]+", "-", co["eng"].lower()).strip("-")[:30] or co["code"])
cdir = ROOT/"companies"/slug; (cdir/"data").mkdir(parents=True, exist_ok=True)

# ---- 2) 설정 생성 (있으면 유지)
GROUPS = {
 "삼성": dict(rx=["삼성", "SDS", "SDI", "물산", "디스플레이", "제일기획", "호텔신라", "에스원", "경제연구소", "인력개발원", "종합기술원", "에버랜드", "제일모직", "웰스토리", "바이오로직스", "바이오에피스"],
            companies="삼성전자|삼성물산|삼성SDS|삼성에스디에스|삼성SDI|삼성디스플레이|삼성전기|삼성생명|삼성화재|삼성카드|삼성증권|삼성중공업|삼성엔지니어링|삼성바이오로직스|삼성바이오에피스|삼성웰스토리|삼성인력개발원|삼성경제연구소|삼성종합기술원|제일기획|호텔신라|에스원|에버랜드|제일모직|삼성테크윈|삼성코닝|삼성전관|삼성종합화학|삼성토탈|일본삼성|삼성네트웍스"),
 "LG": dict(rx=["LG", "엘지", "GS"], companies="LG전자|LG화학|LG디스플레이|LG이노텍|LG유플러스|LG CNS|LG생활건강|LG에너지솔루션|LG경영개발원|LG인화원|LG상사|LG하우시스|LG헬로비전"),
 "SK": dict(rx=["SK", "에스케이"], companies="SK하이닉스|SK텔레콤|SK이노베이션|SK네트웍스|SK C&C|SK에너지|SK E&S|SK브로드밴드|SK케미칼|SK가스|SK건설|SK에코플랜트|SK스퀘어|SK온|SK바이오팜"),
 "현대": dict(rx=["현대", "기아", "HD현대"], companies="현대자동차|기아|현대모비스|현대제철|현대건설|현대글로비스|현대위아|현대오토에버|현대트랜시스|현대카드|현대캐피탈|현대엔지니어링|현대로템|현대중공업|HD현대"),
 "롯데": dict(rx=["롯데"], companies="롯데쇼핑|롯데케미칼|롯데지주|롯데칠성|롯데제과|롯데웰푸드|롯데건설|롯데정보통신|롯데카드|롯데호텔|롯데면세점"),
 "한화": dict(rx=["한화"], companies="한화|한화솔루션|한화에어로스페이스|한화생명|한화손해보험|한화시스템|한화오션|한화토탈|한화호텔앤드리조트"),
 "CJ": dict(rx=["CJ", "씨제이"], companies="CJ제일제당|CJ대한통운|CJ ENM|CJ올리브영|CJ프레시웨이|CJ CGV|CJ올리브네트웍스"),
}
grp = A.group or next((g for g in GROUPS if name.startswith(g)), "none")
core = name[len(grp):] if grp != "none" and name.startswith(grp) else ""
self_variants = {name, name.replace(" ", ""), co["eng"]} | ({f"{grp} {core}"} if core else set())
self_extra = [x for x in A.self_extra.split("|") if x]
self_rx = "|".join(sorted((re.escape(v) for v in self_variants if v), key=len, reverse=True) + self_extra)
if grp != "none":
    alts = []
    for a in GROUPS[grp]["rx"]:
        if a == grp and core: alts.append(f"{grp}(?!{re.escape(core)}" + "".join("|" + x[len(grp):] for x in self_extra if x.startswith(grp) and len(x) > len(grp)) + ")")
        elif a in name or any(re.search(a, x) or re.search(x, a) for x in self_extra): continue   # 자사 전신(제일모직·에버랜드)은 그룹 계열사에서 뺀다
        else: alts.append(a)
    group_rx = "|".join(alts); comp_rx = "|".join(c for c in GROUPS[grp]["companies"].split("|") if c.replace(" ", "") != name.replace(" ", "") and not any(re.search(x, c) for x in self_extra))
else: group_rx = "(?!x)x"; comp_rx = "(?!x)x"   # 그룹 없음: 아무것도 매칭하지 않음
cfg_f = cdir/"config.json"
if not cfg_f.exists():
    cfg = {"slug": slug, "name": name, "corp_code": co["code"], "stock": co["stock"], "db": f"{slug}_exec.db", "logo": pathlib.Path(A.logo).name if A.logo else "",
           "self_regex": self_rx, "group_regex": group_rx, "group_companies_regex": comp_rx, "group_name": grp if grp != "none" else "", "secom": False,
           "title_merge_year": 2021 if grp == "삼성" else None,
           "years": {"first": A.first, "last": datetime.date.today().year - 1, "quarters": [[datetime.date.today().year, c] for c in ("11013", "11012", "11014")], "pay_first": 2015},
           "latest_report": [datetime.date.today().year, "11012"], "first_doc": "(add_company 자동 생성: 미확인)", "affiliates": {}, "affiliate_rules": {}, "affiliate_hint": [],
           "events": ([{"year": 2021, "label": "2021년 12월 정기인사부터 전무 직급 폐지·부사장으로 통합(그룹 인사제도 개편, 외부 보도 기준). 이후 '부사장' 승진은 구 전무 승진일 수 있음", "kind": "title"}] if grp == "삼성" else []),
           "origin_scan": {"scanned": [], "not_available": ["전 직장 공시 추적 미실시"]},
           "sector_rules": [["영업·사업", "영업|사업부|사업팀|지점|지사|고객|Sales|마케팅|상품"], ["생산·제조", "생산|제조|공장|품질|구매|SCM|물류|설비"], ["연구·개발", "연구|개발|R&D|기술|설계|CTO|솔루션"],
                            ["전사 스태프", "경영지원|인사|재무|전략|기획|감사|법무|홍보|커뮤니케이션|준법|IR|총무|경영진단"], ["해외", "법인|해외|미주|구주|유럽|중국|아시아|글로벌"]],
           "_note": f"add_company.py 가 {datetime.date.today()} 생성. self_regex/group_regex/sector_rules 는 1차값이니 확인할 것"}
    cfg_f.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8"); print("config 생성:", cfg_f)
else: print("config 있음(유지):", cfg_f)
if A.logo and pathlib.Path(A.logo).exists(): (cdir/pathlib.Path(A.logo).name).write_bytes(pathlib.Path(A.logo).read_bytes())
gm_f = cdir/"data"/"group_map.json"
if not gm_f.exists():
    gm = {"_설명": f"{name} 1차 범용 규칙(add_company 생성). 선임 당시/직전 보직 문자열을 '출신 그룹'으로 묶는다. rules 첫 매치, overrides 이름별, track_overrides 이름→트랙. 이 회사 조직 어휘로 교정할 것.",
          "rules": [{"match": "정보보호|보안|IT|전산|정보전략|DX|디지털", "group": "IT·정보보호"}, {"match": "경영지원|경영관리|재무|경리|회계|자산|총무|IR", "group": "경영지원·재무"},
                    {"match": "인사|HR|인재|노무|교육|피플", "group": "인사"}, {"match": "전략|기획|혁신|신사업|미래|M&A|사업개발", "group": "전략·기획"},
                    {"match": "감사|진단|준법|법무|컴플라이언스|변호사", "group": "감사·준법"}, {"match": "커뮤니케이션|홍보|PR|대외", "group": "커뮤니케이션"},
                    {"match": "구매|SCM|물류|자재", "group": "구매·SCM·물류"}, {"match": "R&D|연구|개발|기술|설계|솔루션|플랫폼|AI|데이터", "group": "R&D·개발"},
                    {"match": "생산|제조|공장|품질|설비|공정|QA", "group": "생산·제조·품질"}, {"match": "마케팅|상품|브랜드", "group": "마케팅·상품"},
                    {"match": "법인|해외|미주|구주|유럽|중국|인도|베트남|동남아|아시아|글로벌|Global", "group": "해외 법인·글로벌"},
                    {"match": "영업|사업부|사업팀|사업본부|지점|지사|고객|Sales|서비스", "group": "영업·사업"}],
          "overrides": {}, "track_overrides": {}}
    gm_f.write_text(json.dumps(gm, ensure_ascii=False, indent=1), encoding="utf-8"); print("group_map 생성:", gm_f)

# ---- 3) 파이프라인
env = dict(os.environ, COMPANY=slug, PYTHONUTF8="1")
steps = ([] if A.no_fetch else ["fetch_dart.py", "fetch_docs.py", "fetch_pay.py", "fetch_ceo_changes.py", "fetch_affiliates.py"]) + ["parse_exec_docs.py", "parse_pay.py", "analyze.py", "build_data.py", "build_affil.py", "render_app.py"]
for s in steps:
    print(f"\n=== {s}"); t0 = time.time()
    r = subprocess.run([sys.executable, str(ROOT/s)], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = "\n".join((r.stdout or "").strip().split("\n")[-4:]); print(tail)
    if r.returncode != 0: print(r.stderr[-1500:]); sys.exit(f"{s} 실패")
    print(f"({time.time() - t0:.0f}s)")

# ---- 4) 요약 + 검사
import collections
app = json.load(open(cdir/"data"/"app_data.json", encoding="utf-8")); P = app["people"]
print(f"\n##### {name}: 임원 {len(P)}명", dict(collections.Counter(p["track"] for p in P)))
print("사장 계보:", [(p["name"], p["ceo_from"], p["ceo_to"]) for p in sorted([p for p in P if p["track"].startswith("사장(")], key=lambda p: p["ceo_from"] or "")])
print("첫 등장 연도 분포:", sorted(collections.Counter(p["first_report"] for p in P).items()))
L = [p for p in P if p["track"] == "내부 성장 임원"]
print("출신 그룹:", collections.Counter(p["origin_group"] for p in L).most_common())
print("동명이인:", [n for n, c in collections.Counter(p["name"] for p in P).items() if c > 1])
ver = re.search(r"APP_VERSION\s*=\s*'([^']+)'", (ROOT/"app_template.html").read_text(encoding="utf-8")).group(1)
out = ROOT/"dist"/f"App_{name}_{ver}.html"
subprocess.run([sys.executable, str(ROOT/"check_app.py"), str(out), str(cdir/"data"/"app_data.json")], cwd=ROOT, env=env)
print("\n산출물:", out, "\n다음 할 일: companies/%s/data/group_map.json 교정 → COMPANY=%s python build_data.py && python render_app.py" % (slug, slug))
