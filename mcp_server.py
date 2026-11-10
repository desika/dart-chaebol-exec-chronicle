"""dart-chaebol-exec-chronicle MCP server (stdio, JSON-RPC 2.0, standard library only).

Lets an MCP client (Claude Code, Claude Desktop, etc.) search DART companies, build a
company chronicle in the background, and query the resulting executive data.

Run:  python mcp_server.py          (the client launches it; see .mcp.json)
Env:  DART_API_KEY (or dart_key.txt in the repo root)
"""
import sys, os, io, re, json, html, time, zipfile, pathlib, statistics, subprocess, collections, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
COMP = ROOT / "companies"
PY = sys.executable
JOBS = {}  # slug -> {"proc": Popen, "log": path, "started": ts}

# ---------- helpers ----------
def _key():
    sys.path.insert(0, str(ROOT))
    from dart_key import KEY
    return KEY

def _corp_entries():
    cc = COMP / "_corpcode.xml"
    if not cc.exists() or (time.time() - cc.stat().st_mtime) > 30 * 86400:
        key = _key()
        if not key:
            raise RuntimeError("DART_API_KEY not set (or dart_key.txt missing)")
        COMP.mkdir(exist_ok=True)
        b = urllib.request.urlopen("https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key=" + key, timeout=180).read()
        cc.write_bytes(zipfile.ZipFile(io.BytesIO(b)).read("CORPCODE.xml"))
    x = cc.read_text(encoding="utf-8")
    return [dict(corp_code=m.group(1), name=html.unescape(m.group(2)), eng=html.unescape(m.group(3)), stock=m.group(4).strip())
            for m in re.finditer(r"<corp_code>(\d+)</corp_code>\s*<corp_name>([^<]*)</corp_name>\s*<corp_eng_name>([^<]*)</corp_eng_name>\s*<stock_code>([^<]*)</stock_code>", x)]

def _data(slug):
    f = COMP / slug / "data" / "app_data.json"
    if not f.exists():
        raise RuntimeError(f"no built data for '{slug}' (run build_company first)")
    return json.loads(f.read_text(encoding="utf-8"))

def _affil(slug):
    f = COMP / slug / "data" / "affil.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

def _person_brief(p):
    return {k: p.get(k) for k in ("id", "name", "birth_year", "sex", "title", "job", "track", "appt", "appt_est", "appt_age",
                                   "active", "exit_date", "exit_basis", "tenure_years", "nth_year", "grade_title", "grade_nth",
                                   "school", "degree", "major", "grad_year", "region", "mba", "origin_group", "sector",
                                   "post_at_appt", "promotions", "group_affil", "ceo_from", "ceo_to")} | {
        "pay": [(x.get("year"), x.get("total")) for x in (p.get("pay") or [])],
        "severance": p.get("severance_years") or []}

def _person_full(p):
    d = dict(p)
    d.pop("snaps", None)
    return d

def _dist(items, key):
    c = collections.Counter(x.get(key) or "(none)" for x in items)
    return dict(c.most_common())

# ---------- tools ----------
def t_search_company(query):
    q = query.replace(" ", "")
    ents = _corp_entries()
    if re.fullmatch(r"\d{8}", q):
        c = [e for e in ents if e["corp_code"] == q]
    else:
        ql = q.lower()
        c = [e for e in ents if e["name"].replace(" ", "") == q] or \
            [e for e in ents if ql in e["name"].replace(" ", "").lower() or ql in e["eng"].replace(" ", "").lower()]
    c.sort(key=lambda e: (not e["stock"], len(e["name"])))
    return {"count": len(c), "candidates": [dict(e, listed=bool(e["stock"])) for e in c[:15]],
            "note": "pass 'name' exactly or corp_code to build_company; listed companies first"}

def t_list_companies():
    out = []
    for d in sorted(COMP.glob("*/data/app_data.json")):
        try:
            j = json.loads(d.read_text(encoding="utf-8"))
            co = j["company"]; ppl = j["people"]
            out.append({"slug": d.parent.parent.name, "name": co["name"], "corp_code": co["corp_code"], "group": co.get("group_name"),
                        "years": co.get("years"), "people": len(ppl), "active": sum(1 for p in ppl if p.get("active")),
                        "generated": j.get("generated"),
                        "html": [str(h.relative_to(ROOT)) for h in (ROOT / "dist").glob(f"App_{co['name']}_*.html")]})
        except Exception as e:
            out.append({"slug": d.parent.parent.name, "error": str(e)})
    return {"companies": out, "building": {s: ("running" if j["proc"].poll() is None else f"exit {j['proc'].returncode}") for s, j in JOBS.items()}}

def t_build_company(name, slug=None, group=None, first=None, self_alias=None, no_fetch=False):
    if not no_fetch and not _key():
        raise RuntimeError("DART_API_KEY not set (or dart_key.txt missing). Get a free key at https://opendart.fss.or.kr")
    args = [PY, "-u", str(ROOT / "add_company.py"), name]
    if slug: args += ["--slug", slug]
    if group: args += ["--group", group]
    if first: args += ["--first", str(int(first))]
    if self_alias: args += ["--self", self_alias]
    if no_fetch: args += ["--no-fetch"]
    jid = slug or re.sub(r"[^0-9A-Za-z가-힣]+", "_", name)
    if jid in JOBS and JOBS[jid]["proc"].poll() is None:
        return {"job": jid, "status": "already running", "log": str(JOBS[jid]["log"])}
    COMP.mkdir(exist_ok=True)
    log = COMP / f"_build_{jid}.log"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen(args, cwd=str(ROOT), stdout=open(log, "w", encoding="utf-8"), stderr=subprocess.STDOUT, env=env)
    JOBS[jid] = {"proc": proc, "log": log, "started": time.time(), "args": args[2:]}
    return {"job": jid, "status": "started", "pid": proc.pid, "log": str(log),
            "note": "takes 1-20 minutes; poll build_status(job) every minute or so"}

def t_build_status(job=None, tail_lines=25):
    def one(j):
        info = JOBS[j]; p = info["proc"]; rc = p.poll()
        txt = info["log"].read_text(encoding="utf-8", errors="replace") if info["log"].exists() else ""
        lines = txt.splitlines()
        m = re.search(r"slug[=:]\s*(\S+)", txt)
        return {"job": j, "status": "running" if rc is None else ("done" if rc == 0 else f"failed (exit {rc})"),
                "elapsed_sec": int(time.time() - info["started"]), "args": info["args"],
                "slug_hint": (m.group(1) if m else None),
                "log_tail": lines[-int(tail_lines):]}
    if job:
        if job not in JOBS:
            raise RuntimeError(f"unknown job '{job}'; known: {list(JOBS)}")
        return one(job)
    return {"jobs": [one(j) for j in JOBS]}

def t_company_summary(slug):
    d = _data(slug); co = d["company"]; ppl = d["people"]
    appt = [p for p in ppl if p.get("appt_age") and p.get("track") not in ("사외이사·감사",)]
    recent = [p for p in appt if (p.get("appt_year") or 0) >= (co["years"]["last"] - 4)]
    exe = [p for p in ppl if p.get("track") != "사외이사·감사"]
    ceos = _affil(slug).get("s1_ceos") or []
    def med(xs): xs = [x for x in xs if x is not None]; return round(statistics.median(xs), 1) if xs else None
    return {
        "company": co, "generated": d.get("generated"),
        "people": len(ppl), "active": sum(1 for p in ppl if p.get("active")),
        "by_track": _dist(ppl, "track"), "by_title_active": _dist([p for p in ppl if p.get("active")], "title"),
        "by_origin_group": _dist(exe, "origin_group"), "by_sector": _dist(exe, "sector"),
        "by_degree": _dist(exe, "degree"), "by_region": _dist(exe, "region"),
        "top_schools": collections.Counter(p.get("school") for p in exe if p.get("school")).most_common(10),
        "median_appt_age_all": med([p.get("appt_age") for p in appt]),
        "median_appt_age_recent5y": med([p.get("appt_age") for p in recent]),
        "median_tenure_retired": med([p.get("tenure_years") for p in exe if not p.get("active")]),
        "mba_share": round(sum(1 for p in exe if p.get("mba")) / max(1, len(exe)), 3),
        "ceo_succession": ceos,
        "events": d.get("events"), "headcount": d.get("headcount"),
    }

def t_find_person(slug, name, full=False):
    d = _data(slug); q = name.replace(" ", "")
    hits = [p for p in d["people"] if p["name"].replace(" ", "") == q] or [p for p in d["people"] if q in p["name"]]
    return {"count": len(hits), "people": [(_person_full if full else _person_brief)(p) for p in hits[:10]]}

def t_query_people(slug, title=None, track=None, active=None, school=None, degree=None, origin_group=None, sector=None,
                   appt_year_from=None, appt_year_to=None, appt_age_min=None, appt_age_max=None, mba=None,
                   sort="appt", limit=50):
    d = _data(slug); ppl = d["people"]
    def ok(p):
        if title and not re.search(title, p.get("title") or ""): return False
        if track and not re.search(track, p.get("track") or ""): return False
        if active is not None and bool(p.get("active")) != bool(active): return False
        if school and not re.search(school, (p.get("school") or "") + " " + (p.get("school_raw") or "")): return False
        if degree and not re.search(degree, p.get("degree") or ""): return False
        if origin_group and not re.search(origin_group, p.get("origin_group") or ""): return False
        if sector and not re.search(sector, p.get("sector") or ""): return False
        if appt_year_from and (p.get("appt_year") or 0) < int(appt_year_from): return False
        if appt_year_to and (p.get("appt_year") or 9999) > int(appt_year_to): return False
        if appt_age_min and (p.get("appt_age") or 0) < int(appt_age_min): return False
        if appt_age_max and (p.get("appt_age") or 999) > int(appt_age_max): return False
        if mba is not None and bool(p.get("mba")) != bool(mba): return False
        return True
    hits = [p for p in ppl if ok(p)]
    keyf = {"appt": lambda p: p.get("appt") or "", "name": lambda p: p["name"], "birth": lambda p: p.get("birth_year") or 0,
            "tenure": lambda p: -(p.get("tenure_years") or 0), "appt_age": lambda p: p.get("appt_age") or 0}.get(sort, lambda p: p.get("appt") or "")
    hits.sort(key=keyf)
    return {"count": len(hits), "people": [_person_brief(p) for p in hits[:int(limit)]],
            "dist": {"title": _dist(hits, "title"), "track": _dist(hits, "track"), "origin_group": _dist(hits, "origin_group"),
                     "degree": _dist(hits, "degree"), "school": dict(collections.Counter(p.get("school") or "(none)" for p in hits).most_common(10))}}

def t_ceo_succession(slug):
    a = _affil(slug); d = _data(slug)
    return {"company": d["company"]["name"], "ceos": a.get("s1_ceos") or [],
            "pattern": a.get("pattern"), "changes": a.get("changes"), "subsidiaries": list((a.get("ceo_chain") or {}).keys())}

def t_classmates(slug, name=None, school=None):
    d = _data(slug); ppl = {p["id"]: p for p in d["people"]}
    edges = [e for e in d.get("edges", []) if e.get("type") in ("동문", "alumni", "school") or "동문" in str(e.get("label", ""))]
    if name:
        q = name.replace(" ", "")
        ids = {p["id"] for p in ppl.values() if p["name"].replace(" ", "") == q}
        edges = [e for e in edges if e.get("a") in ids or e.get("b") in ids or e.get("source") in ids or e.get("target") in ids]
    groups = collections.defaultdict(list)
    for p in ppl.values():
        if p.get("school") and p.get("degree") and (not school or re.search(school, p["school"])):
            groups[f"{p['school']} {p['degree']}"].append(f"{p['name']}({p.get('grad_year') or '?'})")
    return {"edges": edges[:200], "groups": {k: v for k, v in groups.items() if len(v) >= 2}}

TOOLS = [
    ("search_company", "Search DART corp codes by (partial) company name or 8-digit corp_code. Listed companies come first.",
     {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, lambda a: t_search_company(a["query"])),
    ("list_companies", "List companies already built in companies/ (with people counts, years, HTML paths) and running builds.",
     {"type": "object", "properties": {}}, lambda a: t_list_companies()),
    ("build_company", "Start building a company chronicle in the background (fetch DART → parse → analyze → render HTML). Returns a job id; poll build_status. 1-20 min.",
     {"type": "object", "properties": {"name": {"type": "string", "description": "DART company name (e.g. LG이노텍) or 8-digit corp_code"},
                                       "slug": {"type": "string", "description": "ASCII folder name; default derived from English name"},
                                       "group": {"type": "string", "description": "삼성|LG|SK|현대|롯데|한화|CJ|none (auto when name starts with group)"},
                                       "first": {"type": "integer", "description": "first fiscal year, default 2016"},
                                       "self_alias": {"type": "string", "description": "former names/aliases regex, e.g. 삼성엔지니어링"},
                                       "no_fetch": {"type": "boolean", "description": "skip fetching; re-parse/build/render only"}},
      "required": ["name"]}, lambda a: t_build_company(a["name"], a.get("slug"), a.get("group"), a.get("first"), a.get("self_alias"), a.get("no_fetch", False))),
    ("build_status", "Status and log tail of a build job (or all jobs).",
     {"type": "object", "properties": {"job": {"type": "string"}, "tail_lines": {"type": "integer"}}}, lambda a: t_build_status(a.get("job"), a.get("tail_lines", 25))),
    ("company_summary", "Headline stats for a built company: counts by track/title/origin/degree/region, top schools, median appointment age, CEO succession, events.",
     {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]}, lambda a: t_company_summary(a["slug"])),
    ("find_person", "Find executives by name in a built company. full=true returns the whole record (yearly snapshots excluded).",
     {"type": "object", "properties": {"slug": {"type": "string"}, "name": {"type": "string"}, "full": {"type": "boolean"}}, "required": ["slug", "name"]},
     lambda a: t_find_person(a["slug"], a["name"], a.get("full", False))),
    ("query_people", "Filter executives (regex on title/track/school/degree/origin_group/sector; active; appointment year/age range; mba) and get rows + distributions.",
     {"type": "object", "properties": {"slug": {"type": "string"}, "title": {"type": "string"}, "track": {"type": "string"}, "active": {"type": "boolean"},
                                       "school": {"type": "string"}, "degree": {"type": "string"}, "origin_group": {"type": "string"}, "sector": {"type": "string"},
                                       "appt_year_from": {"type": "integer"}, "appt_year_to": {"type": "integer"}, "appt_age_min": {"type": "integer"}, "appt_age_max": {"type": "integer"},
                                       "mba": {"type": "boolean"}, "sort": {"type": "string", "description": "appt|name|birth|tenure|appt_age"}, "limit": {"type": "integer"}},
      "required": ["slug"]}, lambda a: t_query_people(**{k: v for k, v in a.items() if k in t_query_people.__code__.co_varnames})),
    ("ceo_succession", "CEO (representative director) succession of the company: order, dates, tenure, age, origin.",
     {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]}, lambda a: t_ceo_succession(a["slug"])),
    ("classmates", "University classmate edges (same school + same program) and school/degree groups with 2+ executives.",
     {"type": "object", "properties": {"slug": {"type": "string"}, "name": {"type": "string"}, "school": {"type": "string"}}, "required": ["slug"]},
     lambda a: t_classmates(a["slug"], a.get("name"), a.get("school"))),
]
TOOL_MAP = {n: (d, s, f) for n, d, s, f in TOOLS}

# ---------- JSON-RPC over stdio (newline-delimited) ----------
def _send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n"); sys.stdout.flush()

def _handle(req):
    m = req.get("method"); rid = req.get("id"); prm = req.get("params") or {}
    if m == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": prm.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}}, "serverInfo": {"name": "dart-chaebol-exec-chronicle", "version": "0.9.7"}}}
    if m == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [{"name": n, "description": d, "inputSchema": s} for n, d, s, _ in TOOLS]}}
    if m == "tools/call":
        name = prm.get("name"); args = prm.get("arguments") or {}
        if name not in TOOL_MAP:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown tool {name}"}}
        try:
            out = TOOL_MAP[name][2](args)
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}}
    if m == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if rid is None:
        return None  # notification
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {m}"}}

def main():
    sys.stdin.reconfigure(encoding="utf-8"); sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        resp = _handle(req)
        if resp is not None:
            _send(resp)

if __name__ == "__main__":
    main()
