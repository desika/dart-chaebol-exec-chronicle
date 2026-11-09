"""affil_raw.json → data/affil.json : 자회사별 임원 임기표(대표이사·감사·사내이사), 자사 인물 연결, 패턴 통계, 인선 예측 보드.
   설정 affiliate_rules: {자회사명: {"size": "부사장급|상무급", "fit": "담당업무 적합 정규식"}} (없으면 상무급·적합성 미반영)"""
import json, re, pathlib, collections, datetime, sys
from company import CFG, D, TODAY, THIS_YEAR
CONAME = CFG["name"]; AFR = CFG.get("affiliate_rules", {})
if not (D/"affil_raw.json").exists():
    # 자회사 공시 미수집 회사: 사장 임기표만 만들어 둔다
    people = json.load(open(D/"app_data.json", encoding="utf-8"))["people"]; ceos = []
    for p in people:
        if not p["track"].startswith("사장("): continue
        a = p.get("ceo_from") or p["appt"]; e = p.get("ceo_to") or (None if p["active"] else p["exit_date"])
        ad = datetime.date.fromisoformat(a) if a else None; ed = datetime.date.fromisoformat(e) if e else TODAY
        ceos.append({"name": p["name"], "pid": p["id"], "birth_year": p["birth_year"], "appointed": a, "ended": e, "tenure_years": round((ed - ad).days / 365.25, 1) if ad else None, "age_at": (int(a[:4]) - p["birth_year"]) if (a and p["birth_year"]) else p["appt_age"], "nth": p.get("ceo_nth"), "origin": p.get("origin_note") or p.get("ext_career") or ""})
    ceos.sort(key=lambda x: x["appointed"] or "")
    (D/"affil.json").write_text(json.dumps({"terms": [], "ceo_chain": {}, "ceo_by_year": {}, "changes": [], "s1_ceos": ceos, "pattern": {}, "boards": [], "companies": {}}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("affil_raw 없음 → 사장 임기표만", len(ceos)); sys.exit(0)
raw = json.load(open(D/"affil_raw.json", encoding="utf-8"))
app = json.load(open(D/"app_data.json", encoding="utf-8"))
people = app["people"]; by_name = collections.defaultdict(list)
for p in people: by_name[p["name"]].append(p)
NAME = re.compile(r"^[가-힣]{2,4}$"); DATE = re.compile(r"^(\d{4})\.\s?(\d{1,2})\.\s?(\d{1,2})$")
def d(s):
    m = DATE.match((s or "").strip()); return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None
def pos_norm(s):
    s = (s or "").replace(" ", "")
    if "대표" in s: return "대표이사"
    if "감사" in s: return "감사"
    if "사내이사" in s or s == "이사": return "사내이사"
    if "집행" in s: return "집행임원"
    return s or "?"
rows = []      # 임원 명단(연1회 공시) 행
ceo_by_year = collections.defaultdict(dict)   # company -> year -> ceo
changes = []   # 임원의변동
for rec in raw["filings"]:
    c = rec["company"]; yr = int(rec["rcept_dt"][:4])
    for fn, f in rec["files"].items():
        if rec["kind"] == "audit":
            if f["ceo_mentions"]: ceo_by_year[c][yr] = f["ceo_mentions"][0]
            continue
        for tb in f["tables"]:
            hdr = " ".join(tb[0])
            if rec["kind"] == "annual_group" and "대표자" in hdr:
                for r in tb[1:]:
                    nm = next((x for x in r if NAME.match(x)), None)
                    if nm: ceo_by_year[c].setdefault(yr, nm)
            elif rec["kind"] == "annual_group" and "임원명" in hdr:
                for r in tb[1:]:
                    # 이름 셀 위치 찾기
                    i = next((k for k, x in enumerate(r) if NAME.match(x) and k + 1 < len(r) and re.search(r"(이사|감사|집행|대표)", r[k + 1])), None)
                    if i is None: continue
                    rest = r[i + 1:]
                    dates = [x for x in rest if DATE.match(x.strip())]
                    rows.append({"company": c, "report_year": yr, "name": r[i], "position": pos_norm(rest[0]), "position_raw": rest[0],
                                 "appointed": d(dates[0]) if dates else None, "registered": d(dates[1]) if len(dates) > 1 else None, "term_end": d(dates[2]) if len(dates) > 2 else None,
                                 "concurrent": next((x for x in rest if re.search(r"(계열|이사|대표)", x) and re.search(r"[A-Za-z]{4,}|\(주\)|주식회사", x)), ""),
                                 "prior": next((x for x in rest if CONAME in x or "전 -" in x), ""),
                                 "renew": next((x for x in rest if x in ("신임", "중임")), "")})
            elif rec["kind"] == "exec_change":
                pos = None
                for r in tb[1:]:
                    if r and re.search(r"(이사|감사|집행|대표)", r[0]) and not NAME.match(r[0]): pos = pos_norm(r[0]); r = r[1:]
                    if r and r[0] == "임원명": continue
                    cells_ = [x for x in r if x not in ("-", "")]
                    names = [x for x in r if NAME.match(x)]
                    dates = [x for x in r if DATE.match(x.strip())]
                    career = next((x for x in r if "전 -" in x or "현 -" in x), "")
                    if not names: continue
                    # 변경전(해임) / 변경후(선임) 판별: 날짜 위치
                    out_name = in_name = None
                    # 구조: 임원명|해임일|등기일|임원명|선임일|등기일
                    if len(r) >= 6:
                        if NAME.match(r[0]) and DATE.match(r[1].strip()): out_name, out_date = r[0], d(r[1])
                        if NAME.match(r[3]) and DATE.match(r[4].strip()): in_name, in_date = r[3], d(r[4])
                    changes.append({"company": c, "filed": rec["rcept_dt"], "position": pos, "out": out_name, "out_date": out_date if out_name else None,
                                    "in": in_name, "in_date": in_date if in_name else None, "career": career, "raw": " | ".join(r)})
# ---- 임기표: (회사, 이름, 직위, 선임일) 단위로 합치기
terms = {}
for r in rows:
    k = (r["company"], r["name"], r["position"], r["appointed"])
    t = terms.setdefault(k, {"company": r["company"], "name": r["name"], "position": r["position"], "appointed": r["appointed"], "term_end": None, "prior": "", "concurrent": "", "years": [], "renew": set()})
    t["years"].append(r["report_year"]); t["term_end"] = r["term_end"] or t["term_end"]; t["prior"] = r["prior"] or t["prior"]; t["concurrent"] = r["concurrent"] or t["concurrent"]
    if r["renew"]: t["renew"].add(r["renew"])
terms = sorted(terms.values(), key=lambda t: (t["company"], t["position"] != "대표이사", t["appointed"] or ""))
# 종료일: 임원의변동 해임일 > 다음 보고 연도에 사라짐
for t in terms:
    t["renew"] = sorted(t["renew"]); t["years"] = sorted(set(t["years"]))
    ch = [c for c in changes if c["company"] == t["company"] and c["out"] == t["name"] and c["position"] == t["position"] and c["out_date"]]
    if ch: t["ended"] = ch[0]["out_date"]; t["end_basis"] = "임원의변동 해임일"
    else:
        last = max(t["years"]); latest_year = max(y for c in ceo_by_year for y in ceo_by_year[c])
        t["ended"] = None if last >= latest_year else f"{last + 1}-03-31"; t["end_basis"] = "" if t["ended"] is None else f"{last}년 공시까지 등장(다음 해 주총 전후 종료 추정)"
    # 자사 인물 연결
    cand = by_name.get(t["name"], [])
    t["s1_pid"] = cand[0]["id"] if cand else None
    t["s1_track"] = cand[0]["track"] if cand else None
    t["s1_exit_year"] = cand[0]["exit_year"] if cand else None
    t["s1_birth_year"] = cand[0]["birth_year"] if cand else None
    t["s1_title"] = cand[0]["title"] if cand else None
    ay = int(t["appointed"][:4]) if t["appointed"] else None
    t["age_at"] = (ay - t["s1_birth_year"]) if (ay and t["s1_birth_year"]) else None
    t["gap_from_s1_exit"] = (ay - t["s1_exit_year"]) if (ay and t["s1_exit_year"]) else None
    t["kind"] = ("퇴임 후 자회사 대표" if t["position"] == "대표이사" and cand and not cand[0]["active"] else
                 "현직 겸직" if cand and cand[0]["active"] else (f"{CONAME} 출신" if CONAME in t["prior"] else "기타"))
# 대표이사 승계 체인 (임원의변동 + 감사보고서 + 연1회 대표자)
ceo_chain = collections.defaultdict(list)
for t in terms:
    if t["position"] == "대표이사" or (t["position"] == "사내이사" and any(ceo_by_year[t["company"]].get(y) == t["name"] for y in t["years"])):
        ceo_chain[t["company"]].append(t)
for c in ceo_chain:
    # 같은 이름 중복 제거(대표이사+사내이사 행)
    seen = {};
    for t in ceo_chain[c]:
        k = t["name"];
        if k not in seen or (t["appointed"] or "") < (seen[k]["appointed"] or ""): seen[k] = t
    ceo_chain[c] = sorted(seen.values(), key=lambda t: t["appointed"] or "")
    for i, t in enumerate(ceo_chain[c]):
        if t["ended"] is None and i + 1 < len(ceo_chain[c]): t["ended"] = ceo_chain[c][i + 1]["appointed"]; t["end_basis"] = "후임 선임일"
        a = datetime.date.fromisoformat(t["appointed"]) if t["appointed"] else None
        e = datetime.date.fromisoformat(t["ended"]) if t["ended"] else TODAY
        t["tenure_years"] = round((e - a).days / 365.25, 1) if a else None
# 자사 사장 임기
s1_ceos = []
for p in people:
    if not p["track"].startswith("사장("): continue
    a = p.get("ceo_from") or p["appt"]; e = p.get("ceo_to") or (None if p["active"] else p["exit_date"])
    ad = datetime.date.fromisoformat(a) if a else None; ed = datetime.date.fromisoformat(e) if e else TODAY
    s1_ceos.append({"name": p["name"], "pid": p["id"], "birth_year": p["birth_year"], "appointed": a, "ended": e, "tenure_years": round((ed - ad).days / 365.25, 1) if ad else None, "age_at": (int(a[:4]) - p["birth_year"]) if (a and p["birth_year"]) else p["appt_age"], "nth": p.get("ceo_nth"), "origin": (p["pre_segs"][-1]["company"] + " " + p["pre_segs"][-1]["title"]) if p.get("pre_segs") else (p["ext_career"].split(" / ")[-1] if p["ext_career"] else "")})
s1_ceos.sort(key=lambda x: x["appointed"] or "")
# ---- 패턴 통계
ex_ceos = [t for c in ceo_chain for t in ceo_chain[c] if t["s1_pid"] and t["s1_track"] == "내부 성장 임원"]
def med(a): a = sorted(x for x in a if x is not None); return (a[len(a)//2] if len(a) % 2 else (a[len(a)//2-1]+a[len(a)//2])/2) if a else None
pattern = {"n_ceo_terms": len(ex_ceos), "age_at_median": med([t["age_at"] for t in ex_ceos]), "gap_median": med([t["gap_from_s1_exit"] for t in ex_ceos]),
           "tenure_median": med([t["tenure_years"] for t in ex_ceos if t["ended"]]), "s1_titles": collections.Counter(t["s1_title"] for t in ex_ceos),
           "audit_pattern": [t for t in terms if t["position"] == "감사"]}
pattern["s1_titles"] = dict(pattern["s1_titles"])
# ---- 예측 보드: 다음 공석 + 후보
today = TODAY
boards = []
for c, chain in ceo_chain.items():
    cur = chain[-1]; te = cur.get("term_end")
    # 후보 풀: 내부 성장 현직 임원, 나이·연차로 채점 (경험적: 선임 나이 중앙값 ±2, 상무 4년차 이상/부사장, 사업 적합성)
    cands = []
    size_hint = AFR.get(c, {}).get("size", "상무급")
    for p in people:
        if p["track"] != "내부 성장 임원" or not p["active"]: continue
        yrs = p.get("grade_nth") or (THIS_YEAR - (p["appt_year"] or THIS_YEAR)); tot = THIS_YEAR - (p["appt_year"] or THIS_YEAR); age27 = THIS_YEAR + 1 - (p["birth_year"] or 0)
        s = 0; why = []
        if pattern["age_at_median"]:
            da = abs(age27 - pattern["age_at_median"]);
            if da <= 1: s += 35; why.append(f"선임 나이대 적중({age27}세)")
            elif da <= 3: s += 20; why.append(f"나이 근접({age27}세)")
            elif da <= 5: s += 8
        if "부사장" in p["title"] and (yrs >= 4 or tot >= 8): s += 25; why.append(f"부사장 {yrs}년차·임원 {tot}년차(퇴임 압력)")
        elif "상무" in p["title"] and yrs >= 5: s += 25; why.append(f"상무 {yrs}년차(승진 또는 퇴임)")
        elif "상무" in p["title"] and yrs == 4: s += 12; why.append("상무 4년차")
        if size_hint == "부사장급" and "부사장" in p["title"]: s += 15; why.append("부사장급 자리")
        if size_hint == "상무급" and "상무" in p["title"]: s += 15; why.append("상무급 자리")
        fit = AFR.get(c, {}).get("fit", "")
        if fit and re.search(fit, p["job"] + " " + p["job_hist"]): s += 15; why.append("사업 적합(" + p["job"] + ")")
        if s >= 30: cands.append({"pid": p["id"], "name": p["name"], "birth_year": p["birth_year"], "title": p["title"], "job": p["job"], "appt_year": p["appt_year"], "score": s, "why": why})
    # 이미 퇴임해 자문역 단계인 사람(직전 2년 퇴임, 자회사 미취임)
    recent_exits = [p for p in people if p["track"] == "내부 성장 임원" and not p["active"] and p["exit_year"] and p["exit_year"] >= THIS_YEAR - 1 and not any(t["s1_pid"] == p["id"] for t in terms)]
    for p in recent_exits:
        cands.append({"pid": p["id"], "name": p["name"], "birth_year": p["birth_year"], "title": p["title"] + "(퇴임)", "job": p["job"], "appt_year": p["appt_year"], "score": 40 + (15 if ("부사장" in p["title"]) == (size_hint == "부사장급") else 0), "why": [f"{p['exit_year']}년 퇴임, 자문역 단계로 추정"]})
    cands.sort(key=lambda x: -x["score"])
    boards.append({"company": c, "current": {"name": cur["name"], "appointed": cur["appointed"], "term_end": te, "s1_pid": cur["s1_pid"], "prior": cur["prior"]},
                   "next_window": (te[:7] if te else "임기 미공시") , "size_hint": size_hint, "candidates": cands[:8],
                   "note": f"임기 만료 {te}. 관례상 3월 정기주총에서 교체·중임 결정. 교체 시 직전 12월 {CONAME} 인사에서 퇴임한 {size_hint} 임원이 1순위." if te else "임기 미공시"})
out = {"terms": terms, "ceo_chain": ceo_chain, "ceo_by_year": {c: dict(sorted(v.items())) for c, v in ceo_by_year.items()}, "changes": changes, "s1_ceos": s1_ceos, "pattern": pattern, "boards": boards,
       "companies": raw["companies"]}
(D/"affil.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
with open(D/"_affil_summary.txt", "w", encoding="utf-8") as f:
    for c, chain in ceo_chain.items():
        f.write(f"== {c} 대표이사\n")
        for t in chain: f.write(f"  {t['name']} {t['appointed']}~{t['ended']} ({t['tenure_years']}y) 임기만료 {t['term_end']} | {t['prior']} | 자사:{t['s1_track']} 퇴임{t['s1_exit_year']} 나이{t['age_at']} 간격{t['gap_from_s1_exit']}\n")
    f.write("== 감사/사내이사\n")
    for t in terms:
        if t["position"] != "대표이사": f.write(f"  {t['company']} {t['name']} {t['position']} {t['appointed']}~{t['ended']} 만료{t['term_end']} | {t['prior']} | {t['kind']} | 겸직:{t['concurrent'][:50]}\n")
    f.write(f"== {CONAME} 사장\n")
    for s in s1_ceos: f.write(f"  {s['name']} {s['appointed']}~{s['ended']} ({s['tenure_years']}y) {s['age_at']}세 ← {s['origin']}\n")
    f.write(f"== 패턴 {json.dumps({k: v for k, v in pattern.items() if k != 'audit_pattern'}, ensure_ascii=False)}\n")
    for b in boards:
        f.write(f"== 예측 {b['company']} 현 {b['current']['name']} 만료 {b['current']['term_end']} ({b['size_hint']})\n")
        for cd in b["candidates"]: f.write(f"   {cd['score']:>3} {cd['name']} {cd['birth_year']} {cd['title']} {cd['job']} ← {'; '.join(cd['why'])}\n")
print("terms", len(terms), "changes", len(changes))
