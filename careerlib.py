"""경력 문구 공통 파서(analyze.py·build_data.py가 함께 쓴다).
   - 학력 문장에서 학교/전공/학위 추출(한글·영문)
   - 연도 없는 한 덩어리 경력('…팀장연세대 물리학 석사', '…Manager Harvard Univ. 경영학 석사')의 보직/학력 분리
   영문 학교는 키워드(Univ, Institute, College …) 위치를 먼저 잡고 앞뒤로 제한적으로 넓힌다(직함이 학교명에 딸려 오는 것을 막기 위해)."""
import re

KNOWN_KO = (r"서울시립|서울과학기술|서울산업|한국외국어|한국외|한국항공|한국교원|한국방송통신|한국해양|한국기술교육|서울|연세|고려|성균관|한양|중앙|경희|서강|부산|경북|인하|아주|건국|동국|홍익|숭실|국민|단국|광운|명지|세종|"
            r"이화여|숙명여|서울여|성신여|덕성여|동덕여|전남|전북|충남|충북|영남|계명|동아|부경|울산|강원|인천|가톨릭|한밭|금오공|경상|조선|원광|포항공|경기|경남|창원|순천향|한림|대구|전주|동의|경성|호서|상명|한성|공주|목포|제주|안동|군산|"
            r"육군사관|해군사관|공군사관|카이스트|청주|대전|한남|배재|목원|우송|강릉원주|강릉|부산외|영산|동서|동명|신라|경일|대구가톨릭|한동|선문|남서울|평택|수원|용인|협성|서경|삼육|총신|성공회|을지|고신|인제|가야|진주|한양여|괴테|파리")
KO_KNOWN = rf"(?:(?:{KNOWN_KO})대(?:학교|학원|학)?|한국과학기술원|한국과학기술대|광주과학기술원|대구경북과학기술원|울산과학기술원|한국예술종합학교|KAIST|POSTECH|GIST|DGIST|UNIST)"
KO_GENERIC = r"(?:(?<![가-힣])[가-힣A-Za-z]*\d*대학(?:교|원)?(?![가-힣])|(?<![가-힣])[가-힣]{2,6}대(?![가-힣])|(?<![가-힣])[가-힣]{2,4}실전(?![가-힣]))"
KO_SCHOOL = rf"(?:{KO_KNOWN}|{KO_GENERIC})"
DEGREE = r"(학사|석사|박사|MBA|수료|졸업|중퇴|JD|Ph\.?D\.?)"
MAJOR = r"([가-힣A-Za-z0-9·/&()\-]+(?:\s[가-힣A-Za-z0-9·/&()\-]+){0,2}?)"
EN_KEY = re.compile(r"\b(Univ\.?|University|Universit[aeé]\w*|Institute|Inst\.?|College|School|Sch\.?|Tech\.?|MIT|UCLA|Berkeley|Stanford|Harvard|Princeton|Polytechnic|Academy|Hochschule|NYU|RPI|Caltech)(?=[\s,.(]|$)")
EN_STOP = {"Manager","Director","Scientist","Engineer","Korea","Cloud","Services","Service","LLC","Lab","Labs","Inc","Inc.","Senior","Sr.","Pr.","General","Head","VP","Consultant","Partner","President","Officer","Staff","Research","Researcher","Architect","Lead","Leader","Group","Team","Center","Centre","Co.","Corp.","Ltd.","Ltd","Co","Corp","Global","Division","Business","Intelligence","Data","Software","Systems","Platform","Solutions","Strategy","Marketing","Sales","Web","Amazon","Google","Microsoft","IBM","Oracle","SAP","Accenture","Samsung","Cisco","Intel","Nokia","Ericsson","Fellow"}
DEG_CHAIN = r"(?:\s*(?:학사|석사|박사|졸업|수료|MBA))*"
KO_TAILS = [re.compile(rf"({s})\s*(?:{MAJOR}\s*)?{DEGREE}{DEG_CHAIN}\s*$") for s in (KO_KNOWN, KO_GENERIC)]   # 알려진 학교명 우선(붙어 쓴 '담당고려대' 방지)
KO_ANYS = [re.compile(rf"({s})\s*(?:{MAJOR}\s*)?{DEGREE}?{DEG_CHAIN}") for s in (KO_KNOWN, KO_GENERIC)]
def _first(rxs, t):
    for rx in rxs:
        m = rx.search(t)
        if m: return m
    return None
DEG_TAIL = re.compile(rf"\s*(?:{MAJOR}\s*)?{DEGREE}(?:\s*(?:학사|석사|박사|졸업|수료))*\s*$")
MAJOR_ONLY = re.compile(r"\s*([가-힣A-Za-z·/&()\-]{1,20}(?:학과|학부|학|MBA|전공))\s*$")   # 학위 표기 없이 전공만 붙은 경우('London School of Economics 경제학')
CITY = r"(?:파리|도쿄|런던|베이징|뉴욕|보스턴|상하이|홍콩|싱가포르)\s"
def norm_camel(t):
    """'DirectorUniversity' → 'Director University' (Mc/Mac 접두는 제외)"""
    t = re.sub(r"([가-힣])([A-Z])", lambda m: m.group(1) + " " + m.group(2), t or "")   # '그룹장University' → '그룹장 University'
    return re.sub(r"(?<!Mc)(?<!Mac)([a-z])([A-Z][a-z])", lambda m: m.group(1) + " " + m.group(2), t)

def _camel_tail(tok):
    """'ManagerMassachusetts' → 'Massachusetts' (소문자→대문자 경계에서 뒷부분만)"""
    m = re.search(r"[a-z][A-Z]", tok)
    return tok[m.start() + 1:] if m else tok

def find_en_school(t):
    """영문 학교명 구간 (start, end, school) — 끝에서 가장 가까운 키워드 기준. 없으면 None"""
    keys = list(EN_KEY.finditer(t))
    for km in keys:
        # 키워드 뒤: 'of X', ', City' 같은 연결만 허용
        end = km.end()
        tail = re.match(r"(?:\s?(?:of|de|at|the|and|&|for|in)\s?[A-Z&][A-Za-z.&'\-()]*)*(?:,?\s[A-Z][A-Za-z.&'\-()]*(?![가-힣])){0,3}", t[end:])
        if tail: end += tail.end()
        rest = t[end:]
        if not (rest.strip() == "" or DEG_TAIL.match(rest) or MAJOR_ONLY.match(rest)): continue
        # 키워드 앞: 대문자 시작 토큰 최대 4개, 정지어·쉼표 끝·한글 만나면 중단
        start = km.start(); toks = []
        for tok in reversed(re.findall(r"\S+", t[:start])):
            if len(toks) >= 4: break
            ct = _camel_tail(tok)
            if ct in ("of","de","at","the","and","&","for","in"): toks.insert(0, ct); continue
            if not re.match(r"[A-Z]", ct) or re.search(r"[가-힣]", ct) or ct.rstrip(".,") in EN_STOP or tok.endswith(","): break
            toks.insert(0, ct)
            if ct != tok: break   # 붙어 있던 토큰은 뒷부분만 쓰고 중단
        while toks and toks[0] in ("of","de","at","the","and","&","for","in"): toks.pop(0)
        school = (" ".join(toks) + " " + t[km.start():end]).strip() if toks else t[km.start():end].strip()
        start = len(t[:end]) - len(school) if t[:end].endswith(school) else t.rfind(school, 0, end)
        return (start, end, school.strip(" ,"))
    return None

def split_edu_tail(items):
    """[(연도|None, 문장)] 중 연도 없는 단일 항목이면 끝의 학력을 떼어 [보직, 학력]로 만든다."""
    if len(items) != 1 or items[0][0] is not None: return items
    t = norm_camel(items[0][1]); cut = None
    m = _first(KO_TAILS, t)
    if m:
        cut = m.start(); cm = re.search(CITY + r"$", t[:cut])
        if cm: cut = cm.start()
    else:
        en = find_en_school(t)
        if en and DEG_TAIL.match(t[en[1]:] or " 졸업") and (t[en[1]:].strip() != "" or True): cut = en[0]
    if cut is None: return items
    head = t[:cut].strip(" ,·-"); edu = t[cut:].strip()
    if not head or re.fullmatch(r"\d{4}\s*[年년]?", head): return items
    return [(None, head), (None, edu)]

def parse_edu(e):
    """학력 문장 → (학교, 전공, 학위). 못 찾으면 ('', '', '')"""
    e = norm_camel(re.sub(r"^\d{4}\s*[年년]?\s*", "", e or "").strip()); e = re.sub(r"\((학사|석사|박사|MBA)\)", r" \1", e)
    cm = re.match(r"^([日佛美英獨中加豪伊西瑞])\s*(.*)$", e); country = {"日":"일본","佛":"프랑스","美":"미국","英":"영국","獨":"독일","中":"중국","加":"캐나다","豪":"호주","伊":"이탈리아","西":"스페인","瑞":"스위스"}.get(cm.group(1)) if cm else None
    if cm: e = cm.group(2)
    am = re.match(r"^((?:HEC|LSE|INSEAD|IE|IESE|ESSEC|ESCP|Sup de Pub(?:\(佛\))?|Ontario College|Central Michigan 대학)\b[A-Za-z. ]*?)\s+(.*)$", e)   # 약칭·비정형 학교
    if am:
        rest = am.group(2); dm = DEG_TAIL.match(" " + rest) or re.match(r"\s*" + MAJOR + r"\s*" + DEGREE + r"?", " " + rest)
        school = am.group(1).strip() + (f"({country})" if country else ""); major = (dm.group(1) or "") if dm else ""; degree = (dm.group(2) or "") if (dm and dm.lastindex and dm.lastindex >= 2) else ""
        return school, re.sub(r"^(졸업|수료)$", "", major.strip()), degree.strip()
    _res = _parse_edu_core(e)
    if _res[0] and country and country != "미국": return (_res[0] + f"({country})", _res[1], _res[2])
    return _res
def _parse_edu_core(e):
    m = _first(KO_TAILS, e) or _first(KO_ANYS, e)
    if m and not (m.start() > 0 and re.search(r"[A-Za-z]", e[:m.start()])):   # 앞에 영문 학교가 따로 있으면 영문 쪽 우선
        school, major, degree = m.group(1), m.group(2) or "", m.group(3) or ""
    else:
        en = find_en_school(e)
        if not en:
            if m: school, major, degree = m.group(1), m.group(2) or "", m.group(3) or ""
            else: return "", "", ""
        else:
            school = en[2]; dm = DEG_TAIL.match(e[en[1]:]); mo = MAJOR_ONLY.match(e[en[1]:]) if not dm else None; major = (dm.group(1) or "") if dm else (mo.group(1) if mo else ""); degree = (dm.group(2) or "") if dm else ""
    school = re.sub(r"\s+(MBA|석사|박사|학사)$", "", school.strip(" ,"))
    major = re.sub(r"^(졸업|수료)$", "", re.sub(r"^(대학원|일반대학원|경영대학원|경영전문대학원)\s*", "", (major or "").strip()))
    return school, major, degree.strip()

if __name__ == "__main__":
    tests = ["서울대학교 경영학과 졸업", "1986년 서울대 경영학과 석사", "경북대 전자통신학과 졸업(학사, 석사)", "SCL사업부 GL사업개발팀장 고려대 마케팅학 석사",
             "물류사업부 기획팀장KAIST MBA 석사", "경영지원실 경영관리팀장 Helsinki Sch of Economics&Business Administration MBA 석사", "전략마케팅실장 파리 제6대학 전산학 박사",
             "MIT Lincoln Lab Staff Scientist Harvard Univ. 컴퓨터과학 박사", "Microsoft General ManagerMassachusetts Inst. of Tech. MBA", "삼성전자 전략1팀 Univ. of Michigan, Ann Arbor 경영학 석사",
             "Cloud IntelligenceDuke Univ 전기공학 박사", "Google Cloud Korea, 대표괴테대 컴퓨터공학 석사", "클라우드서비스사업부 Gen.AI사업팀 Gen.AI아키텍처그룹장 NYU 수학과 박사", "SDSI법인장 한국과학기술원 경영공학 박사",
             "Accenture, Managing DirectorUniversity of Illinois, Urbana-Champaign 경영학 석사", "삼성전자 메모리사업부장", "Rensselaer Polytechnic Inst.(RPI) 기계공학 박사", "Indiana Univ. Bloomington Global MBA 석사 졸업", "인디애나대 경영학 박사"]
    for t in tests:
        print(f"{t!r:95} -> split {split_edu_tail([(None, t)])}  edu {parse_edu(split_edu_tail([(None, t)])[-1][1])}")

# ---- 학력이 문장 앞에 오는 형식(제일기획: "Boston Univ. 신문방송학(석사) 제일기획 디지털부문장", "고려대 경영학 석사 제일기획 …", "佛 HEC MBA(석사) …")
COUNTRY_PFX = r"(?:[日佛美英獨中加豪伊西瑞]\s*)?"
SCHOOL_HINT = re.compile(r"(" + KO_KNOWN + r"|대학교|대학원|대학|대\b|공대|실전|전문대|Univ|University|College|School|Institute|Inst\.|Tech|KAIST|POSTECH|HEC|LSE|MIT|Academy|Polytechnic|Hochschule|Sup de Pub|고\b)", re.I)
HEAD_DEG = re.compile(r"\((?:학사|석사|박사|MBA)\)|(?<![가-힣A-Za-z])(?:학사|석사|박사|졸업|졸|수료|MBA)(?![가-힣A-Za-z])")
HEAD_MAJOR = re.compile(r"^(" + COUNTRY_PFX + r".{2,60}?(?:학과|학부|학|MBA|전공|과정))\s+(\S.*)$")
def split_edu_head(items):
    """연도 없는 단일 항목이 학력으로 시작하면 [학력, 보직]으로 나눈다. 앞 60자 안의 학위 표식(…(석사)·석사·졸) 또는 전공 어미(…학) 뒤에서 자른다."""
    if len(items) != 1 or items[0][0] is not None: return items
    t = re.sub(r"\((학사|석사|박사|MBA)\)", r" \1", norm_camel(items[0][1]).strip())   # '신문방송학(석사)' → '신문방송학 석사'
    ms = [m for m in HEAD_DEG.finditer(t) if m.end() <= 70 and SCHOOL_HINT.search(t[:m.start()])]
    m = ms[-1] if ms else None   # 'MBA 석사'처럼 학위 표식이 연달아 오면 마지막 것까지 학력
    if m:
        edu, rest = t[:m.end()].strip(), t[m.end():].strip(" ,·")
    else:
        mm = HEAD_MAJOR.match(t)
        if not (mm and SCHOOL_HINT.search(mm.group(1))): return items
        edu, rest = mm.group(1).strip(), mm.group(2).strip()
    if not rest: return [(None, edu)]
    return [(None, edu), (None, rest)]
