"""University of Leeds parser."""
import re
from urllib.parse import urlparse

from parsers.base import BaseParser
from parsers.models import (CalendarData, DeadlineData, DiscoveredPage,
                            ModuleData, ModuleRef, ProgramData)
from parsers.page import norm_ws, parse_date
from parsers.uk.common import (date_range,
                               dedupe_discovered, facts, fee_near, ielts,
                               event_type, keyword_check, known_name, pick,
                               section_text, title_from, unwrap_funnelback)
from config.codes import Category, UniCode

PG_AWARDS = r"MSc|MA|MBA|LLM|MRes|MEd|MPH|PGDip|PGCert|Masters"


class Leeds(BaseParser):
    uni_code = UniCode.LEEDS

    def program_catalog(self, page, res):
        seen = set()
        for a in page.soup.find_all("a", href=True):
            url = _canonical_detail(unwrap_funnelback(page.abs(a["href"])))
            if _is_detail(url) and url not in seen:
                seen.add(url)
                res.discovered.append(DiscoveredPage(
                    url=url, category=Category.PROGRAM_DETAIL,
                    title=norm_ws(a.get_text(" ", strip=True)) or None))
            elif "course-search/" in url and ("start_rank=" in url or "page=" in url):
                res.discovered.append(DiscoveredPage(
                    url=url, category=Category.PROGRAM_CATALOG, title="Course search page"))
        dedupe_discovered(res.discovered)
        if not res.discovered:
            res.note("未解析出 Leeds 课程链接")

    def program_detail(self, page, res):
        name = title_from(page, suffix_re=r"\s*\|\s*University of Leeds.*$")
        if not name:
            res.note("未解析出课程标题")
            return
        f = facts(page)
        p = ProgramData(name_en=name, level=_level(name, page.url),
                        url=page.url, entry_year=_entry_year(page.url, page.txt, self.entry_year))
        p.ucas_code = pick(f, "ucas code")
        p.duration = pick(f, "duration", "course duration")
        p.entry_req_text = pick(f, "entry requirements", "entry requirement")
        p.tuition_home = fee_near(page.txt, ("UK fees", "Home fees", "UK:"))
        p.tuition_intl = fee_near(page.txt, ("International fees", "International:"))
        taught_by = page.re(r"This course is taught by\s*\n([^\n]+)", flags=re.I)
        p.faculty = known_name(self.conf.faculties, taught_by or page.txt)
        p.dept = taught_by if taught_by and not p.faculty else pick(f, "school", "department")
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        self._deadlines(page, p)
        self._modules(page, p)
        if p.tuition_intl is None:
            p.notes.append("未解析出国际学费")
        res.programs.append(p)

    def _deadlines(self, page, p):
        for raw in re.findall(r"\b\d{1,2} \w+ 20\d{2}\b", page.txt):
            win = _window(page.txt, raw).lower()
            d = parse_date(raw)
            if d and "deadline" in win and "international" in win:
                p.deadlines.append(DeadlineData(
                    "international", "application", d + " 23:59:00", p.entry_year, "国际申请截止"))

    def _modules(self, page, p):
        area = section_text(page, r"Course details and modules|Modules", limit=9000)
        for line in [norm_ws(x) for x in re.split(r"\n| {2,}", area or "") if norm_ws(x)]:
            m = re.match(r"(.{5,120}?)\s+(?:[–-]|\()\s*(\d{1,3})\s+credits?\)?$", line, re.I)
            if m and not re.search(r"\b(year|semester|choose|select)\b", m.group(1), re.I):
                p.modules.append(ModuleRef(name=norm_ws(m.group(1)), module_type="core"))

    # ---------------- 官方课程目录（名单+链接，不镜像详情）----------------
    # catalogue.leeds.ac.uk 全开放无反爬（探明 2026-07-04，学年 202627 生效）。
    # 表单页 /ModuleSearch/{UG|TP} 枚举 School 下拉（~147 代码）→ 结果页
    # GET /ModuleSearch/results/{level}/{year}/ALL/{SCHOOL}/False/ALL/False
    # 每行 = 代码链接 + 课名；学院名在区块 h2（含联办区块，同院照收）。
    CATALOGUE = "https://catalogue.leeds.ac.uk"
    CATALOGUE_YEAR = "202627"
    MODULE_LEVELS = ("UG", "TP")     # 本科 + 授课研究生

    def module_catalog(self, page, res):
        if "/ModuleSearch/results/" in page.url:
            dept = None
            for h2 in page.soup.select("h2"):
                t = norm_ws(h2.get_text(" ", strip=True))
                if t and not t.startswith("Taught by") and "navigation" not in t.lower():
                    # 区块标题多为正规院系名（loader 按名复用已有行）；
                    # 教学单元名（如 Health Economics）走 faculty_alias 映射，
                    # 别名表外且无结构词的不作归属
                    if (t in (self.conf.faculty_alias or {})
                            or re.search(r"\b(School|Faculty|Institute|Centre|Department)\b", t)):
                        dept = t
                    break
            lvl = page.url.split("/ModuleSearch/results/")[1].split("/")[0]
            for a in page.soup.select('a[href^="/Module/"]'):
                code = norm_ws(a.get_text(" ", strip=True))
                # 课名 = 代码链接所在单元格的下一格（列数随页面变化，别按下标取）
                cell = a.find_parent("td")
                nxt = cell.find_next_sibling("td") if cell else None
                name = norm_ws(nxt.get_text(" ", strip=True)) if nxt else ""
                if not re.fullmatch(r"[A-Z]{2,6}\d{4}[A-Z]?", code) or not name:
                    continue
                res.modules.append(ModuleData(
                    name_en=name, url=page.abs(a["href"]), entry_year=self.entry_year,
                    code=code, dept=dept, level="PGT" if lvl == "TP" else lvl))
            if not res.modules:
                res.note("目录结果页无课程行（该学院×层级可能确实无课）")
            return
        # 表单页：School 下拉 → 各学院结果页任务
        codes = {str(o.get("value") or "").strip()
                 for o in page.soup.select('select#School option')}
        codes = {c for c in codes if re.fullmatch(r"[A-Z]{2,6}", c)}
        for code in sorted(codes):
            for lvl in self.MODULE_LEVELS:
                res.discovered.append(DiscoveredPage(
                    url=(f"{self.CATALOGUE}/ModuleSearch/results/{lvl}/"
                         f"{self.CATALOGUE_YEAR}/ALL/{code}/False/ALL/False?keyMatch=any"),
                    category=Category.MODULE_CATALOG,
                    title=f"{code} 课程名单（{lvl}）"))
        if not res.discovered:
            res.note("目录表单页未枚举到 School 下拉（站点结构变了？）")

    def term_dates(self, page, res):
        """版式（实测 2026-07）：'Autumn term:' 标签行，日期区间在下一行；
        学年在页首 'Academic year 2026/27'。"""
        ym = page.re(r"Academic year\s+(20\d{2}/\d{2})")
        if not ym:
            res.note("Leeds term dates 未见 'Academic year' 学年标识")
            return
        label = None
        for line in page.txt.splitlines():
            line = norm_ws(line)
            start, end = date_range(line)
            if start:
                if label:
                    res.calendar.append(CalendarData(
                        ym, event_type(label, start), label, start, end))
                    label = None
                continue
            if 3 <= len(line) <= 60 and not re.search(r"\d{4}", line):
                label = line.rstrip(":")
        if not res.calendar:
            res.note("Leeds term dates 未解析出日期")

    def ug_admissions(self, page, res):
        for raw in re.findall(r"\b\d{1,2} \w+ 20\d{2}\b", page.txt):
            d = parse_date(raw)
            if d and "UCAS" in _window(page.txt, raw):
                res.deadlines.append(DeadlineData(
                    "all", "equal_consideration", d + " 18:00:00", self.entry_year, "UCAS 日期"))

    def pg_admissions(self, page, res):
        res.info("Leeds PGT 截止日期主要在课程页解析")

    def china_page(self, page, res):
        keyword_check(res, page, r"China", "Leeds 中国专页")

    def faculty_list(self, page, res):
        if not known_name(self.conf.faculties, page.txt):
            res.note("未匹配到 Leeds Faculty 名称")


def _is_detail(url):
    p = urlparse(url)
    return p.netloc == "courses.leeds.ac.uk" and bool(
        re.search(r"^/(?:20\d{4}/)?[a-z]\d{3,4}/[a-z0-9-]+/?$", p.path))


def _canonical_detail(url):
    p = urlparse(url)
    m = re.match(r"^/20\d{4}/([a-z]\d{3,4}/[a-z0-9-]+)/?$", p.path)
    if p.netloc == "courses.leeds.ac.uk" and m:
        return f"{p.scheme or 'https'}://{p.netloc}/{m.group(1)}"
    return url


def _level(name, url):
    return "PGT" if "/masters" in url or re.search(rf"\b(?:{PG_AWARDS})\b", name) else "UG"


def _entry_year(url, txt, default):
    m = re.search(r"/(20\d{2})\d{2}/", url)
    return m.group(1) if m else default


def _window(txt, needle, size=220):
    pos = txt.find(needle)
    return norm_ws(txt[max(0, pos - size):pos + size]) if pos >= 0 else ""
