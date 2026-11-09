"""단일 파일 앱 렌더 검사: 현직자만 on/off 두 상태로 전원 상세(viewPerson) + 탭 7개를 호출해 JS 오류가 없는지 본다.
   사용: python check_app.py <앱.html> <app_data.json>   (종료코드 0 = 이상 없음)"""
import sys, json, pathlib, subprocess, re, tempfile, os
html, data = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
ids = [p["id"] for p in json.load(open(data, encoding="utf-8"))["people"]]
inj = ("<script>setTimeout(()=>{const bad=[];for(const flag of [false,true]){VIEW.activeOnly=flag;for(const id of " + json.dumps(ids, ensure_ascii=False) +
       "){try{viewPerson(id)}catch(e){bad.push(flag+' '+id+': '+e.message)}}for(const v of ['viewTimeline','viewPeople','viewOrigins','viewPay','viewAffil','viewNetwork','viewAbout']){try{window[v]()}catch(e){bad.push(flag+' '+v+': '+e.message)}}}"
       "document.title='ZZ '+(bad.length?bad.slice(0,8).join(' / '):'none');},800)</script>")
import tempfile; tmp = pathlib.Path(tempfile.gettempdir())/"_check_app.html"; prof = pathlib.Path(tempfile.gettempdir())/"_check_edge_profile"
tmp.write_text(html.read_text(encoding="utf-8").replace("</body>", inj + "</body>"), encoding="utf-8")
edge = next((p for p in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"] if os.path.exists(p)), None)
if not edge: print("Edge 없음"); sys.exit(2)
out = subprocess.run([edge, "--headless", "--disable-gpu", f"--user-data-dir={prof}", "--virtual-time-budget=30000", "--dump-dom", "file:///" + str(tmp).replace("\\", "/") + "#/people"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
tmp.unlink(missing_ok=True)
m = re.search(r"<title>ZZ ([^<]*)", out)
res = m.group(1) if m else "(제목 없음: 페이지 로드 실패)"
print(f"{html.name}: {len(ids)}명 × 2상태 + 탭 7개 → {res}")
sys.exit(0 if res.strip() == "none" else 1)
