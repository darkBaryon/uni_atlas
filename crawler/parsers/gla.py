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
from parsers.base import (DeadlineData, DiscoveredPage, ParseResult,
                          ProgramData, register)


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

    # ---- 院系：页面正文首个 'School of X'（推断值，仅供范围参考）----
    m = re.search(r"School of ([A-Z][A-Za-z &,]+?)(?:[.\n]| launched| offers| at | is )", txt)
    if m:
        p.dept = "School of " + m.group(1).strip().rstrip(",")

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
