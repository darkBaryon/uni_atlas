"""UCL 解析器（选择器实测于 2026-07 试点，详见 ARCHITECTURE.md）。

- program_detail: 专业页 → ProgramData（学费/要求/日期/模块表）
- program_catalog: 目录页 → DiscoveredPage（div.result-item 学位卡 + 分页）
- module_catalog: 模块页 → ModuleData（学分/负责人/考核占比/大纲）
"""
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config
from parsers.base import (CalendarData, DeadlineData, DiscoveredPage,  # noqa: F401
                          ModuleData, ModuleRef, ParseResult, ProgramData,
                          register)

MODULE_CODE_RE = re.compile(r"-([A-Z]{4}\d{4})/?$")


def _dt(s):
    """'20 Oct 2025' / '20 October 2025' -> '2025-10-20'"""
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _money(s):
    m = re.search(r"£([\d,]+)", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def _entry_year(url, fee_year_label):
    if fee_year_label:                       # '2026/27' -> '2026'
        return fee_year_label.split("/")[0]
    m = re.search(r"-(\d{4})/?$", url)       # slug 结尾 '...-bsc-2026'
    return m.group(1) if m else config.DEFAULT_ENTRY_YEAR


@register("ucl", "program_detail")
def parse_program(html, url):
    soup = BeautifulSoup(html, "html.parser")
    txt = soup.get_text("\n", strip=True)
    res = ParseResult()

    name = None
    h1 = soup.find("h1")
    if h1:
        name = re.sub(r"\s+", " ", h1.get_text(strip=True))
    if not name:
        res.notes.append("页面无 h1 标题，可能非专业页")
        return res

    level = "UG" if "/undergraduate/" in url else "PGT"
    p = ProgramData(name_en=name, level=level, url=url,
                    entry_year=config.DEFAULT_ENTRY_YEAR)

    # ---- 学费/学制: .study-mode 元素 + 前置标签判断含义 ----
    for el in soup.select(".study-mode"):
        prev = el.find_previous(["dt", "h4", "h5", "strong", "th"])
        label = prev.get_text(strip=True) if prev else ""
        val = el.get_text(strip=True)
        if "UK tuition" in label:
            p.tuition_home = _money(val)
            m = re.search(r"\((\d{4}/\d{2})\)", label)
            p.fee_year_label = m.group(1) if m else None
            if p.tuition_home is None and val:
                p.notes.append(f"UK 学费非标准格式，原文: {val[:200]}")
        elif "Overseas tuition" in label:
            p.tuition_intl = _money(val)
            if p.tuition_intl is None and val:
                p.notes.append(f"Overseas 学费非标准格式，原文: {val[:200]}")
        elif label == "Duration" and not p.duration:
            p.duration = val
    p.entry_year = _entry_year(url, p.fee_year_label)

    # ---- 语言等级 / 学位要求 / UCAS / 校区 ----
    m = re.search(r"English language level for this (?:course|programme) is:?\n?\s*(Level \d)", txt)
    p.language_band = ("level-" + m.group(1)[-1]) if m else None
    m = re.search(r"(?:minimum of an?|Normally a minimum of an?)\s+"
                  r"([^.\n]*(?:class|degree|Honours)[^.\n]*)", txt)
    if m:
        p.entry_req_text = m.group(1).strip()[:300]
    m = re.search(r"UCAS(?: course)? code\n?\s*([A-Z0-9]{4,5})", txt)
    p.ucas_code = m.group(1) if m else None
    m = re.search(r"(?:Campus|Location)\n([^\n]+)", txt)
    p.campus = m.group(1) if m else None

    # ---- 申请窗口：签证/非签证双轨（PGT）+ UCAS Apply by（UG） ----
    m = re.search(r"require a visa:\s*\n?(\d{1,2} \w{3,9} \d{4})\s*\n?–\s*\n?"
                  r"(\d{1,2} \w{3,9} \d{4})", txt)
    if m and "do not require" not in txt[max(0, m.start()-40):m.start()]:
        p.app_open_date = _dt(m.group(1))
        end = _dt(m.group(2))
        if end:
            p.deadlines.append(DeadlineData(
                "international", "application", end + " 17:00:00",
                p.entry_year, "需签证申请者截止"))
    m = re.search(r"do not require a visa:\s*\n?(\d{1,2} \w{3,9} \d{4})\s*\n?–\s*\n?"
                  r"(\d{1,2} \w{3,9} \d{4})", txt)
    if m:
        end = _dt(m.group(2))
        if end:
            p.deadlines.append(DeadlineData(
                "home", "application", end + " 17:00:00",
                p.entry_year, "无需签证申请者截止"))
    m = re.search(r"UCAS[^\n]*\n?\s*Apply by\s*\n?\s*(\d{1,2} \w+ \d{4})", txt)
    if m:
        d = _dt(m.group(1))
        if d:
            p.deadlines.append(DeadlineData(
                "all", "equal_consideration", d + " 18:00:00",
                p.entry_year, "UCAS 常规截止"))

    # ---- 模块表：优先 module-catalogue 链接（带代码），退化到纯文本行 ----
    def grab(cls, mtype):
        for sec in soup.select(f".{cls}"):
            links = sec.select('a[href*="/module-catalogue/modules/"]')
            if links:
                for a in links:
                    href = urljoin(url, a["href"])
                    mm = MODULE_CODE_RE.search(href)
                    p.modules.append(ModuleRef(
                        name=re.sub(r"\s+", " ", a.get_text(strip=True)),
                        code=mm.group(1) if mm else None,
                        url=href, module_type=mtype))
                continue
            for line in sec.get_text("\n", strip=True).split("\n"):
                mm = re.match(r"^(.{4,120}?)\s*\(([A-Z]{4}\d{4})\)\s*$", line)
                if mm:
                    p.modules.append(ModuleRef(mm.group(1), mm.group(2),
                                               module_type=mtype))
                elif (re.match(r"^[A-Z][^.]{6,90}$", line)
                      and not re.search(r"module|credit|Students|You |The |All "
                                        r"|Please|Optional|Compulsory|For more", line)):
                    p.modules.append(ModuleRef(line, module_type=mtype))
    grab("prog-modules-mandatory", "core")
    grab("prog-modules-optional", "optional")

    if p.tuition_intl is None and not p.modules:
        p.notes.append("学费与模块均未解析出，页面结构可能已变，需人工核对")
    res.programs.append(p)
    return res


@register("ucl", "program_catalog")
def parse_catalog(html, url):
    """目录页 → 学位卡 div.result-item 展开为 program_detail 任务 + 下一页。"""
    soup = BeautifulSoup(html, "html.parser")
    res = ParseResult()
    for item in soup.select("div.result-item"):
        a = item.find("a", href=True)
        if not a:
            continue
        href = urljoin(url, a["href"]).split("#")[0]
        if "/degrees/" not in href and "/taught-degrees/" not in href:
            continue
        name = re.sub(r"\s+", " ", a.get_text(strip=True))
        dept_el = item.select_one("span.search-results__dept")
        dept = dept_el.get_text(strip=True) if dept_el else None
        res.discovered.append(DiscoveredPage(
            url=href, category="program_detail", title=name,
            note=dept, crawl_freq="monthly"))
    nxt = soup.select_one('a[rel="next"], li.pager__item--next a')
    if nxt and nxt.get("href"):
        res.discovered.append(DiscoveredPage(
            url=urljoin(url, nxt["href"]), category="program_catalog",
            title="目录分页", crawl_freq="manual"))
    if not res.discovered:
        res.notes.append("目录页未解析出学位卡（result-item），页面结构可能已变")
    return res


@register("ucl", "module_catalog")
def parse_module(html, url):
    """模块详情页；目录根页（搜索界面）不在此解析。"""
    res = ParseResult()
    if "/module-catalogue/modules/" not in url:
        res.notes.append("module-catalogue 根页为搜索界面，模块任务由专业页链接自动登记")
        return res

    soup = BeautifulSoup(html, "html.parser")
    txt = soup.get_text("\n", strip=True)
    h1 = soup.find("h1")
    name = re.sub(r"\s+", " ", h1.get_text(strip=True)) if h1 else None
    if not name:
        res.notes.append("模块页无标题，跳过")
        return res

    mm = MODULE_CODE_RE.search(url)
    mod = ModuleData(name_en=name, url=url, entry_year=config.DEFAULT_ENTRY_YEAR,
                     code=mm.group(1) if mm else None)

    def kv(label):
        m = re.search(label + r":?\s*\n([^\n]+)", txt)
        return m.group(1).strip() if m else None

    credits = kv(r"Credit value")
    mod.credits = int(credits) if credits and credits.isdigit() else None
    m = re.search(r"(FHEQ Level \d+)", txt)
    mod.level = m.group(1) if m else None
    mod.leader = kv(r"Module leader")
    mod.semester = kv(r"(?:Intended t|T)eaching term") or kv(r"Term")
    mod.prerequisites = kv(r"(?:Module p|P)rerequisites?")

    # 考核占比：形如 "75% Exam" 的行；同一模块按多个 delivery 重复列出需去重
    seen, ass = set(), []
    for w, t in re.findall(r"\n(\d{1,3})%\s*\n?([A-Z][^\n%]{2,60})", txt):
        key = (int(w), t.strip().lower())
        if key not in seen:
            seen.add(key)
            ass.append({"weight": int(w), "type": t.strip()})
    mod.assessment = ass or None

    # 大纲：Description 标题后的正文
    desc_el = soup.select_one(".module-description, .field--name-body")
    if desc_el:
        mod.description = desc_el.get_text("\n", strip=True)[:8000]
    else:
        m = re.search(r"\nDescription\n(.{100,8000}?)(?:\nKey information\n|"
                      r"\nAssessment\n|\nOther information\n|$)", txt, re.S)
        mod.description = m.group(1).strip() if m else None
    if not mod.description:
        mod.notes.append("未解析出大纲正文")
    if mod.credits is None:
        mod.notes.append("未解析出学分")

    res.modules.append(mod)
    return res
