"""格拉斯哥大学解析器（选择器实测于 2026-07 样本页）。

页面特点（对比 UCL）：
- 目录页 ul.programme-list：纯 <li><a>Name[MSc/PgDip]</a></li>，卡上无院系 →
  范围过滤靠专业名关键词（见 gla.yaml scope 注释）；
- 专业页 h1 是栏目名（"Postgraduate study"），真实项目名在 <title> 尾段；
- 费用/截止/雅思都在专业页集中呈现，文本模式固定，PGT 页最好抓；
- UG 专业页不标学费数额（指向统一的 fee status 页），UCAS code 形如 GN42。
"""
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config
from parsers.base import (CalendarData, DeadlineData, DiscoveredPage,
                          ParseResult, ProgramData, register)


def _default_year():
    u = config.uni("gla")
    return u.entry_year if u else config.DEFAULT_ENTRY_YEAR


def _dt(s):
    """'24 August 2026' / '24 Aug 2026' -> '2026-08-24'"""
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _norm(s):
    return re.sub(r"\s+", " ", s.lower().replace(" and ", " & ")).strip()


def _canon_school(txt):
    """把正文里的 School 提及匹配到 gla.yaml 的官方清单；匹配不上返回 None。"""
    u = config.uni("gla")
    if not u or not u.faculties:
        return None
    canon = {_norm(k): k for k in u.faculties}
    for m in re.finditer(r"(Adam Smith Business School|School of [A-Z][A-Za-z ,&\-]{3,70})", txt):
        cand = _norm(m.group(0))
        for nk, name in canon.items():
            if cand == nk or cand.startswith(nk):
                return name
    return None


@register("gla", "program_catalog")
def parse_catalog(html, url):
    """UG/PGT 目录（ul.programme-list）→ program_detail 任务。"""
    soup = BeautifulSoup(html, "html.parser")
    res = ParseResult()
    is_pg = "/postgraduate/" in url
    pat = (re.compile(r"/postgraduate/taught/[a-z0-9-]+/?$") if is_pg
           else re.compile(r"/undergraduate/degrees/[a-z0-9-]+/?$"))
    seen = set()
    for a in soup.select("ul.programme-list a[href]"):
        href = urljoin(url, a["href"]).split("#")[0]
        if not pat.search(href) or href in seen:
            continue
        seen.add(href)
        # 卡片文本 'Data Analytics[MSc: Online distance learning]' → 名称 + 学位
        raw = re.sub(r"\s+", " ", a.get_text(strip=True))
        m = re.match(r"^(.*?)\[(.*?)\]$", raw)
        name, degrees = (m.group(1).strip(), m.group(2).strip()) if m else (raw, "")
        res.discovered.append(DiscoveredPage(
            url=href, category="program_detail",
            title=f"{name} [{degrees}]" if degrees else name,
            crawl_freq="monthly"))
    if not res.discovered:
        res.notes.append("目录页未解析出 programme-list 项目链接，页面结构可能已变")
    return res


@register("gla", "program_detail")
def parse_program(html, url):
    soup = BeautifulSoup(html, "html.parser")
    txt = soup.get_text("\n", strip=True)
    res = ParseResult()

    # 项目名：<title> 'University of Glasgow - Postgraduate study - ... - Data Analytics'
    name = soup.title.get_text().split(" - ")[-1].strip() if soup.title else None
    if not name or len(name) < 3:
        res.notes.append("未从 <title> 解析出项目名，可能非专业页")
        return res

    is_pg = "/postgraduate/" in url
    p = ProgramData(name_en=name, level="PGT" if is_pg else "UG", url=url,
                    entry_year=_default_year())

    # ---- 申请季 + 学费（PGT 页固定文本模式；UG 页无数额，留 None）----
    m = re.search(r"Tuition fees for (\d{4})-\d{2}", txt)
    if m:
        p.entry_year = m.group(1)
        p.fee_year_label = m.group(0).replace("Tuition fees for ", "")
    m = re.search(r"Home & RUK\s*\n(?:Full-time fee:\s*\n)?£([\d,]+)", txt)
    p.tuition_home = float(m.group(1).replace(",", "")) if m else None
    m = re.search(r"International & EU\s*\n(?:Full-time fee:\s*\n)?£([\d,]+)", txt)
    p.tuition_intl = float(m.group(1).replace(",", "")) if m else None

    # ---- 学制：'MSc: \n 12 months full-time'；UG 从 UCAS 行 '(4 years)' ----
    m = re.search(r"\n(?:MSc|MRes|MEd|LLM|MBA|MLitt|MMus)[^\n]*:\s*\n(\d+ months? [a-z -]+)", txt)
    if m:
        p.duration = m.group(1)
    elif not is_pg:
        m = re.search(r"\((\d) years?\)", txt)
        p.duration = f"{m.group(1)} years" if m else None

    # ---- 学术要求 / 雅思 ----
    m = re.search(r"Entry requirements\s*\nfor entry in (\d{4})", txt)
    if m and not is_pg:
        p.entry_year = m.group(1)   # UG 页申请季标在要求区块（如 'for entry in 2027'）
    m = re.search(r"Entry requirements\s*\n(?:for entry in \d{4}\s*\n)?([^\n]{10,300})", txt)
    p.entry_req_text = m.group(1).strip() if m else None
    m = re.search(r"IELTS[^\n]*\n?[^\n]*?(\d\.\d|\d) (?:overall )?with no subtests?"
                  r"(?: less than| under) (\d\.\d|\d)", txt)
    if m:
        p.ielts_overall, p.ielts_min_each = float(m.group(1)), float(m.group(2))

    # ---- 院系：正文里的 School 提及规范化到官方清单（防止句子片段进院系表）----
    p.dept = _canon_school(txt)

    # ---- 截止日期 ----
    if is_pg:
        # 'Application deadlines \n International & EU applicants \n 24 August 2026 \n Home applicants \n 24 August 2026'
        m = re.search(r"International & EU applicants\s*\n(\d{1,2} \w+ \d{4})", txt)
        if m and _dt(m.group(1)):
            p.deadlines.append(DeadlineData(
                "international", "application", _dt(m.group(1)) + " 23:59:00",
                p.entry_year, "国际/欧盟申请者截止"))
        m = re.search(r"Home applicants\s*\n(\d{1,2} \w+ \d{4})", txt)
        if m and _dt(m.group(1)):
            p.deadlines.append(DeadlineData(
                "home", "application", _dt(m.group(1)) + " 23:59:00",
                p.entry_year, "本土申请者截止"))
    else:
        # UG 走 UCAS，截止日期不带年份（'13 January: all other UK applicants'），
        # 年份 = 申请季年（入学当年 1 月截止）
        m = re.search(r"(\d{1,2} January)\s*\n?:?\s*\n?all other", txt, re.I)
        if m:
            d = _dt(f"{m.group(1)} {p.entry_year}")
            if d:
                p.deadlines.append(DeadlineData(
                    "all", "equal_consideration", d + " 18:00:00",
                    p.entry_year, "UCAS 常规截止"))
        m = re.search(r"(\d{1,2} \w+)\s*\n?:?\s*\n?international students", txt, re.I)
        if m:
            d = _dt(f"{m.group(1)} {p.entry_year}")
            if d:
                p.deadlines.append(DeadlineData(
                    "international", "application", d + " 23:59:00",
                    p.entry_year, "国际学生截止"))
        m = re.search(r"Apply to ([A-Z]{1,2}\d{2}[A-Z0-9]?)\b", txt)
        p.ucas_code = m.group(1) if m else None

    if p.tuition_intl is None and is_pg:
        p.notes.append("未解析出国际学费，页面结构可能已变，需人工核对")
    res.programs.append(p)
    return res


@register("gla", "term_dates")
def parse_term_dates(html, url):
    """sessiondates 根页 → 各学年子页任务；学年子页表格 → 校历事件。

    子页表格列：[年, 月, 星期, 日, 教学事件, 假期事件]，年/月为空表示沿用上一行；
    事件是 'Start of X' / 'End of X'（或 'X starts/ends'）的时间点，配对成区间。
    """
    res = ParseResult()
    soup = BeautifulSoup(html, "html.parser")

    m = re.search(r"session(\d{4})-(\d{2})/?$", url)
    if not m:   # 根页：发现各学年子页
        seen = set()
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"]).split("#")[0]
            if re.search(r"/sessiondates/session\d{4}-\d{2}/?$", href) and href not in seen:
                seen.add(href)
                res.discovered.append(DiscoveredPage(
                    url=href, category="term_dates",
                    title=a.get_text(strip=True), crawl_freq="monthly"))
        if not res.discovered:
            res.notes.append("sessiondates 根页未发现学年子页链接")
        return res

    year_label = f"{m.group(1)}/{m.group(2)}"
    table = soup.find("table")
    if not table:
        res.notes.append("学年页无日期表格")
        return res

    # 1) 表格 → 时间点/区间序列。两种历史格式：
    #    A（当年页）: [年, 月, 星期, 日, 教学事件, 假期事件]，年/月空则沿用上行
    #    B（未来页）: [完整日期或日期区间, 事件]，如 'Monday 7 - Friday 18 December 2026'
    points, ranges, year, month = [], [], None, None

    def iso(day, mon, yr):
        try:
            return datetime.strptime(f"{day} {mon} {yr}", "%d %B %Y").strftime("%Y-%m-%d")
        except ValueError:
            return None

    for tr in table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if len(cells) >= 5:          # 格式 A
            year = cells[0] or year
            month = cells[1] or month
            if cells[3].isdigit() and year and month:
                date = iso(cells[3], month, year)
                if date:
                    for text in cells[4:6]:
                        if text:
                            points.append((date, text))
        elif len(cells) == 2:        # 格式 B
            dtxt, ev = cells
            mr = re.match(r"\w+ (\d{1,2})(?: (\w+))?(?: (\d{4}))? ?- ?\w+ (\d{1,2}) (\w+) (\d{4})$", dtxt)
            if mr:                   # 日期区间 'Mon 30 November - Fri 11 December 2026'
                d1 = iso(mr.group(1), mr.group(2) or mr.group(5), mr.group(3) or mr.group(6))
                d2 = iso(mr.group(4), mr.group(5), mr.group(6))
                if d1 and d2:
                    ranges.append((ev, d1, d2))
                continue
            ms = re.match(r"\w+ (\d{1,2}) (\w+) (\d{4})$", dtxt)
            if ms:
                date = iso(ms.group(1), ms.group(2), ms.group(3))
                if date:
                    points.append((date, ev))

    # 2) Start/End 配对成区间；配不上的保留为单日事件
    events, opens = [], []
    for date, text in points:
        ms = re.match(r"Start of (.+)$", text) or re.match(r"(.+?) starts$", text)
        if ms:
            opens.append([ms.group(1).strip(), date])
            continue
        me = re.match(r"End of (.+?)(?: / .*)?$", text) or re.match(r"(.+?) ends$", text)
        if me:
            key = me.group(1).strip().lower()
            hit = next((o for o in opens
                        if o[0].lower().startswith(key) or key.startswith(o[0].lower())), None)
            if hit:
                opens.remove(hit)
                events.append((hit[0], hit[1], date))
            else:
                events.append((text, date, None))
            continue
        events.append((text, date, None))
    events.extend(("Start of " + name, start, None) for name, start in opens)
    events.extend(ranges)   # 格式 B 的现成日期区间

    # 同学年同名事件（如两个毕业典礼期）加月份后缀区分，避免唯一键互相覆盖
    seen_names = {}
    disamb = []
    for name, start, end in sorted(events, key=lambda e: e[1]):
        if name in seen_names:
            name = f"{name} ({datetime.strptime(start, '%Y-%m-%d').strftime('%b')})"
        seen_names[name] = 1
        disamb.append((name, start, end))
    events = disamb

    def etype(name, start):
        n = name.lower()
        if "teaching" in n:
            return "teaching_period"
        if "examination" in n or "revision" in n:
            return "resit_period" if start[5:7] in ("07", "08") else "exam_period"
        if "vacation" in n:
            return "closure"
        if "holiday" in n:
            return "holiday"
        if "graduation" in n:
            return "graduation"
        if "welcome" in n:
            return "welcome_week"
        if "academic year" in n:      # 学年整体区间（9月至次年9月）
            return "other"
        if "orientation" in n:
            return "welcome_week"
        return "other"

    for name, start, end in events:
        res.calendar.append(CalendarData(
            academic_year=year_label, event_type=etype(name, start),
            name=name, start_date=start, end_date=end))
    if not res.calendar:
        res.notes.append("学年页表格未解析出任何事件")
    return res
