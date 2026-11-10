---
name: dart-chaebol-exec-chronicle
description: Build and query the executive chronicle of any Korean listed company from DART filings. Use when the user names a Korean company (삼성전자, LG이노텍, SK하이닉스, 현대자동차 …) and wants its executives, CEO succession, promotion ages, schools/degrees, pay or severance, year-end personnel changes, or an "임원 도감" / executive timeline HTML. Also use for "임원 학력", "사장 계보", "연말 인사", "누가 승진했나", "chaebol executives".
---

# dart-chaebol-exec-chronicle skill

This repository rebuilds every executive's career of a Korean listed company from DART (금융감독원 전자공시) and renders a single HTML "임원 도감". Code only; data is produced locally.

## Prerequisites

1. Python 3.10+. No packages.
2. A DART API key: env `DART_API_KEY`, or `dart_key.txt` in the repo root (git-ignored). Free at https://opendart.fss.or.kr. If missing, tell the user how to get one and stop.
3. On Windows set `PYTHONUTF8=1` before running scripts.

## Workflow

### A. Build a company (first time)

1. Resolve the company. If the MCP server is connected use `search_company`; otherwise run `python add_company.py <이름>` and read the "후보:" line. Prefer listed companies. Renamed companies keep their corp_code: use the current name and pass the old name with `--self`.
2. Run the build. MCP: `build_company(name, slug?, group?, first?, self_alias?)` then poll `build_status` about once a minute. CLI: `python add_company.py <이름> [--slug x] [--group 삼성|LG|SK|현대|롯데|한화|CJ|none] [--first 2016] [--self 옛이름]`. Takes 1–20 minutes; say so.
3. When done, report: people count, active count, CEO succession, the HTML path `dist/App_<회사>_<버전>.html`, and the "미분류" (unclassified origin group) list printed at the end.
4. Offer the grouping fix: edit `companies/<slug>/data/group_map.json` (`rules` = regex on the post held at appointment → origin group, first match wins; `overrides` = per-name). Then rebuild without fetching:
   ```
   set COMPANY=<slug>
   python build_data.py && python build_affil.py && python render_app.py
   ```

### B. Answer questions about a built company

Use the MCP tools when connected (`company_summary`, `query_people`, `find_person`, `ceo_succession`, `classmates`). Without MCP, read `companies/<slug>/data/app_data.json` (`people[]` records, `company`, `events`) and `affil.json` (`s1_ceos`) directly with Python; never load it into the conversation whole, filter first.

Typical questions and where the answer is:

| Question | Source |
|---|---|
| Who are the current executives / by title | `people[].active`, `title`, `job` |
| At what age do people become executives | `appt_age` (median, by year `appt_year`) |
| CEO lineage, tenure, where they came from | `affil.json: s1_ceos` (`origin`, `tenure_years`, `age_at`) |
| Schools, degrees, majors, MBA, overseas | `school`, `degree`, `major`, `region`, `mba` |
| Origin unit (R&D / sales / staff) and division | `origin_group`, `sector`, `post_at_appt` |
| Promotions and years in current title | `promotions`, `title_hist`, `nth_year`, `grade_nth` |
| Who retired when, with severance | `active=false`, `exit_date`, `exit_basis`, `severance_years`, `pay_detail` |
| Pay | `pay[]` (억 원, only ≥5억 disclosed), `pay_detail{year}` (백만 원) |
| Same school + same program | `edges[]`, `classmates` tool |

Always state the rule behind a number when it is an estimate: appointment dates marked `appt_est` are "≤ first disclosed year"; retirement month comes from the severance-disclosure rule; origin group is text-inferred.

### C. Render / check

`python render_app.py` (needs `COMPANY`), `python check_app.py` (Windows Edge headless; reports JS errors). Open the HTML by path for the user.

## Rules of thumb

- Same person = name + birth year-month. If two records look like one person with a birth-month typo, say so instead of merging by hand.
- Do not invent numbers. If a field is empty in the data, the filing did not disclose it.
- Keep company data out of git: `companies/*` and `dist/` are ignored on purpose.
