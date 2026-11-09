"""app_template.html + <data>/app_data.json(+affil.json) → dist/App_{회사명}_{버전}.html (단일 파일, 서버 불필요). 회사 선택: 환경변수 COMPANY=<slug>"""
import pathlib, re, base64, mimetypes
from company import CFG, D, CDIR, ROOT
tpl = (ROOT/"app_template.html").read_text(encoding="utf-8")
ver = re.search(r"APP_VERSION\s*=\s*'([^']+)'", tpl).group(1)
data = (D/"app_data.json").read_text(encoding="utf-8").replace("</script", "<\\/script")
affil = (D/"affil.json").read_text(encoding="utf-8").replace("</script", "<\\/script") if (D/"affil.json").exists() else "{}"
logo_tag = ""
lf = CDIR/CFG["logo"] if CFG.get("logo") else None
if lf and lf.exists():
    mime = mimetypes.guess_type(lf.name)[0] or "image/png"
    logo_tag = f'<img class="logo" src="data:{mime};base64,{base64.b64encode(lf.read_bytes()).decode()}" alt="{CFG["name"]}">'
out = tpl.replace("{{CO_NAME}}", CFG["name"]).replace("{{CO_LOGO}}", logo_tag).replace("/*__DATA__*/", data).replace("/*__AFFIL__*/", affil)
dist = ROOT/"dist"; dist.mkdir(exist_ok=True)
name = f"App_{CFG['name']}_{ver}.html"
(dist/name).write_text(out, encoding="utf-8")
print(dist/name, len(out))
