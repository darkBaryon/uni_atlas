"""英国大学公共提取函数库。

与 generic.py 的分工：本文件是**函数库**（fee_near/ielts/scan_term_lines/...），
专属解析器（ucl.py 等）和声明式通用解析器（generic.py）都从这里取件；
generic.py 是一个**完整解析器**，只服务「零 Python、纯 YAML」的学校。
新逻辑何时下沉到这里：两所以上学校出现同款提取需求时。

Keep this file boring: selectors and school-specific rules stay in each parser.
"""
import re

from config.codes import EventType
from urllib.parse import parse_qs, unquote, urlparse, urlsplit, urlunsplit

from parsers.page import money, norm_ws, parse_date


def clean_url(url, keep_query=False):
    parts = urlsplit(url)
    path = parts.path.rstrip("/") + ("/" if parts.path.rstrip("/") else "")
    query = parts.query if keep_query else ""
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def title_from(page, bad_h1=(), suffix_re=None):
    candidates = []
    h1_el = page.soup.find("h1")
    h1 = norm_ws(h1_el.get_text(" ", strip=True)) if h1_el else None
    if h1 and h1.lower() not in {x.lower() for x in bad_h1}:
        candidates.append(h1)
    meta = page.soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        candidates.append(meta["content"])
    if page.soup.title:
        candidates.append(page.soup.title.get_text(" ", strip=True))
    for text in candidates:
        if suffix_re:
            text = re.sub(suffix_re, "", text, flags=re.I)
        text = norm_ws(text)
        if text:
            return text
    return None


def find_links(page, href_re):
    seen = set()
    for a in page.soup.find_all("a", href=True):
        url = page.abs(a["href"])
        if not re.search(href_re, url, re.I):
            continue
        url = clean_url(url)
        if url in seen:
            continue
        seen.add(url)
        yield url, norm_ws(a.get_text(" ", strip=True)), a


def facts(page):
    out = {}
    for dl in page.soup.find_all("dl"):
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            key = norm_ws(dt.get_text(" ", strip=True)).rstrip(":").lower()
            val = norm_ws(dd.get_text(" ", strip=True))
            if key and val and key not in out:
                out[key] = val
    return out


def pick(mapping, *labels):
    for label in labels:
        key = label.lower()
        if key in mapping:
            return mapping[key]
    for key, val in mapping.items():
        if any(label.lower() in key for label in labels):
            return val
    return None


def first(txt, *patterns, flags=re.I):
    for pattern in patterns:
        m = re.search(pattern, txt or "", flags)
        if m:
            return norm_ws(m.group(1) if m.groups() else m.group(0))
    return None


# 学费语境的排除词：这些词附近的 £ 金额不是学费
_FEE_EXCLUDE = ("deposit", "application fee", "scholarship", "discount",
                "bursar", "living cost", "accommodation", "per year for books")
# 英国大学学年学费的合理区间（区间外视为误抓：奖学金/杂费/总生活费等）
_FEE_MIN, _FEE_MAX = 3500, 70000


def _fee_ok(val, ctx):
    if val is None or not (_FEE_MIN <= val <= _FEE_MAX):
        return False
    low = ctx.lower()
    return not any(w in low for w in _FEE_EXCLUDE)


def fee_near(txt, labels):
    """学费标签附近取 £ 金额；排除奖学金/押金等语境并限定合理区间。"""
    for label in labels:
        for hit in re.finditer(re.escape(label), txt or "", re.I):
            tail = (txt or "")[hit.end():hit.end() + 500]
            val = money(tail)
            if _fee_ok(val, tail[:160]):
                return val
    lines = (txt or "").splitlines()
    for i, line in enumerate(lines):
        if "£" not in line:
            continue
        ctx = " ".join(lines[max(0, i - 4):i + 2])
        if any(label.lower() in ctx.lower() for label in labels):
            val = money(line)
            if _fee_ok(val, ctx):
                return val
    for label in labels:
        m = re.search(re.escape(label) + r"[^£]{0,220}(£\s*[\d,]+(?:\.\d{1,2})?)",
                      txt or "", re.I | re.S)
        if m:
            val = money(m.group(1))
            if _fee_ok(val, m.group(0)):
                return val
    return None


def ielts(txt):
    """IELTS 提及附近取 (总分, 单项最低)。

    只认雅思有效分数区间 4.0–9.0，且优先带小数点形式（'6.5'），
    避免 '4 years'、'2 semesters' 之类的整数污染最低分。
    """
    nums: list[float] = []
    for m in re.finditer(r"IELTS.{0,260}", txt or "", re.I | re.S):
        seg = m.group(0)
        vals = [float(x) for x in re.findall(r"\b([4-9]\.[05])\b", seg)]
        if not vals:  # 个别学校写整分（'IELTS 7'）：仅在无小数形式时退化接受
            vals = [float(x) for x in re.findall(r"\bIELTS\D{0,30}\b([4-9])\b", seg)]
        nums.extend(v for v in vals if 4.0 <= v <= 9.0)
    if not nums:
        return None, None
    return max(nums), min(nums) if len(set(nums)) > 1 else None


def section_text(page, heading_re, stop_re=None, limit=800):
    heading = page.soup.find(re.compile(r"h[1-6]"), string=re.compile(heading_re, re.I))
    if heading:
        parts: list[str] = []
        for node in heading.find_all_next(["h2", "h3", "h4", "p", "li", "td"]):
            if node is heading:
                continue
            if node.name in ("h2", "h3", "h4"):
                if stop_re is None or parts or re.search(stop_re, node.get_text(" ", strip=True), re.I):
                    break
            if node.name in ("p", "li", "td"):
                text = norm_ws(node.get_text(" ", strip=True))
                if text:
                    parts.append(text)
            if len(" ".join(parts)) > limit:
                break
        if parts:
            return " ".join(parts)[:limit]
    if stop_re:
        m = re.search(heading_re + r"\s*\n(.{20," + str(limit) + r"}?)(?=\n" + stop_re + r"|\Z)",
                      page.txt, re.I | re.S)
    else:
        m = re.search(heading_re + r"\s*\n(.{20," + str(limit) + r"}?)(?:\n[A-Z][^\n]{2,80}\n|\Z)",
                      page.txt, re.I | re.S)
    return norm_ws(m.group(1))[:limit] if m else None


def date_loose(text):
    text = norm_ws(text or "")
    text = re.sub(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+", "",
                  text, flags=re.I)
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.I)
    return parse_date(text)


def date_range(text):
    clean = norm_ws((text or "").replace("\u2013", "-").replace("\u2014", "-"))
    clean = re.sub(r"\([^)]*\)", "", clean)
    # 星期前缀（'Monday 30 November - Friday 11 ...'）会挡住区间正则，先剥掉
    clean = re.sub(r"\b(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+", "", clean, flags=re.I)
    m = re.search(r"(\d{1,2})(?:\s+([A-Za-z]+))?(?:\s+(20\d{2}))?\s*(?:-|to)\s*"
                  r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", clean, re.I)
    if m:
        start_month = m.group(2) or m.group(5)
        start_year = m.group(3) or m.group(6)
        return (date_loose(f"{m.group(1)} {start_month} {start_year}"),
                date_loose(f"{m.group(4)} {m.group(5)} {m.group(6)}"))
    dates = re.findall(r"\b\d{1,2}\s+[A-Za-z]+\s+20\d{2}\b", clean)
    if len(dates) >= 2:
        return date_loose(dates[0]), date_loose(dates[1])
    if len(dates) == 1:
        d = date_loose(dates[0])
        return d, d
    return None, None


# 校历事件分类词典（按序首中即停；措辞是数据，见 ARCHITECTURE 七点六）
_EVENT_RULES: tuple = (
    (("welcome", "induction"),                EventType.WELCOME_WEEK),
    # 学年整体区间（"academic year 9月至次年9月"）必须先于 orientation：
    # "academic year / Orientation" 是全年区间，不是迎新周
    (("academic year",),                      EventType.OTHER),
    (("orientation",),                        EventType.WELCOME_WEEK),
    (("reading week",),                       EventType.READING_WEEK),
    (("resit",),                              EventType.RESIT_PERIOD),
    (("exam", "assessment", "revision"),      EventType.EXAM_PERIOD),
    (("holiday",),                            EventType.HOLIDAY),
    (("vacation", "closure", "break"),        EventType.CLOSURE),
    (("graduation",),                         EventType.GRADUATION),
    (("term", "semester", "teaching"),        EventType.TEACHING_PERIOD),
)
RESIT_MONTHS = ("07", "08")   # 英国主考试在春/冬，7-8 月的考试期即补考季


def event_type(name, start=None):
    """事件名（+起始月辅助）→ EventType；词典见 _EVENT_RULES。"""
    n = (name or "").lower()
    for keywords, etype in _EVENT_RULES:
        if any(k in n for k in keywords):
            if etype is EventType.EXAM_PERIOD and start and start[5:7] in RESIT_MONTHS:
                return EventType.RESIT_PERIOD
            return etype
    return EventType.OTHER


def known_name(names, text):
    """在正文中匹配官方院系名；带词边界，长名优先。

    纯子串匹配会让 'School of Art' 吞掉 'School of Arts and Cultures'（实测 bug）；
    词边界挡住复数/延长形，长名优先保证清单内互为前缀时取最长命中。
    """
    if not names or not text:
        return None
    hay = norm_ws(text).lower().replace(" and ", " & ")
    for name in sorted(names, key=len, reverse=True):
        needle = norm_ws(name).lower().replace(" and ", " & ")
        if re.search(re.escape(needle) + r"(?![a-z])", hay):
            return name
    return None


def unwrap_funnelback(url):
    parsed = urlparse(url)
    if "funnelback" not in parsed.netloc:
        return url.split("#")[0]
    target = parse_qs(parsed.query).get("url", [None])[0]
    return unquote(target).split("#")[0] if target else ""


# ---------------- 以下为 2026-07 复审时从各校解析器下沉的共用逻辑 ----------------

def band(txt, letters="A-E", prefix="band"):
    """语言分级提取：'Band C' -> 'band-C'（KCL Band A-E、华威 Band A-C 等）。"""
    m = re.search(r"\bBand\s+([" + letters + r"])\b", txt or "", re.I)
    return f"{prefix}-{m.group(1).upper()}" if m else None


def standard_deadlines(page, p, DeadlineData):
    """课程页常见的两类截止：UCAS 常规 + 'application deadline/closing date'。"""
    d = page.date(r"UCAS[^\n]{0,120}?(\d{1,2} \w+ \d{4})", flags=re.I)
    if d:
        p.deadlines.append(DeadlineData(
            "all", "equal_consideration", d + " 18:00:00", p.entry_year, "UCAS 常规截止"))
    for raw in re.findall(r"(?:application deadline|closing date)[^\n]{0,120}"
                          r"(\d{1,2} \w+ \d{4})", page.txt, re.I):
        d = parse_date(raw)
        if d:
            p.deadlines.append(DeadlineData(
                "all", "application", d + " 23:59:00", p.entry_year, "课程页申请截止"))


def scan_term_lines(page, res, CalendarData, keyword_re, year_re=r"(20\d{2})\s*[/-]\s*(\d{2})"):
    """逐行扫校历：行内含日期区间 + 关键词即记为事件；学年从行内/上文捕获。

    KCL/华威/利兹/伯明翰的校历页都是这种"标题行带学年、条目行带日期"的松散排版。
    """
    year = None
    for line in page.txt.splitlines():
        m = re.search(year_re, line)
        if m:
            year = f"{m.group(1)}/{m.group(2)}"
        start, end = date_range(line)
        if year and start and re.search(keyword_re, line, re.I):
            name = norm_ws(re.sub(r"\d{1,2}.*$", "", line).strip(" :-")) or "Term date"
            res.calendar.append(CalendarData(year, event_type(name, start), name, start, end))


def keyword_check(res, page, pattern, label):
    """参考页体检：关键词还在就静默，消失则告警（页面改版信号）。"""
    if not re.search(pattern, page.txt, re.I):
        res.note(f"{label} 未匹配到关键词 {pattern!r}，页面可能已改版")


def dedupe_discovered(items):
    """DiscoveredPage 按 URL 去重（保序）。"""
    seen: set[str] = set()
    out = []
    for d in items:
        if d.url not in seen:
            seen.add(d.url)
            out.append(d)
    items[:] = out


def modules_from_credit_lis(page, p, ModuleRef, scope_css="li"):
    """通用课程名单提取：'<li>课程名 (15 credits)</li>' 版式（格拉/谢菲实测 2026-07）。

    仅匹配整行恰为「名称 (N credits)」的元素，入学要求里的学分句子不会误中。
    """
    seen = {m.name.lower() for m in p.modules}
    for li in page.soup.select(scope_css):
        t = norm_ws(li.get_text(" ", strip=True))
        m = re.match(r"^(.{3,120}?)\s*\((\d{1,3})\s*[Cc]redits?\)$", t)
        if not m:
            continue
        name = m.group(1).strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        head = li.find_previous(["h3", "h4", "h5", "strong"])
        mtype = ("optional" if head is not None
                 and re.search(r"optional", head.get_text(" ", strip=True), re.I)
                 else "core")
        p.modules.append(ModuleRef(name=name, module_type=mtype))
