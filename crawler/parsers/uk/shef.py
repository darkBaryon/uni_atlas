"""University of Sheffield parser."""
import re

from parsers.base import BaseParser
from parsers.models import CalendarData, DeadlineData, DiscoveredPage, ModuleRef, ProgramData
from parsers.page import norm_ws
from parsers.uk.common import (date_loose, date_range, event_type, find_links,
                               ielts, keyword_check, section_text, title_from)
from config.codes import UniCode

COURSE_RE = r"/(?:undergraduate/courses|postgraduate/taught/courses)/20\d{2}/[^/?#]+/?$"
FACULTY_RE = r"Faculty of (?:Arts and Humanities|Engineering|Health|Science|Social Sciences)|International Faculty, CITY College"

# 集中截止日期页的措辞词典（实测 2026-07）：官网表格描述列 → (类型, 受众判断)
# 措辞是解析器的"翻译词典"数据，集中放表顶，逻辑不再直接内嵌字符串
DEADLINE_KEYWORDS = (
    # (描述列须含的措辞元组,   deadline_type, 受众规则: fixed 或 'visa_check')
    (("deposit deadline",),                        "deposit",     "international"),
    (("applications close", "last date to apply"), "application", "visa_check"),
)


class Sheffield(BaseParser):
    uni_code = UniCode.SHEF

    def program_catalog(self, page, res):
        for url, title, _ in find_links(page, COURSE_RE):
            res.discovered.append(DiscoveredPage(
                url=url, category="program_detail", title=title or None))
        if not res.discovered:
            res.note("Sheffield 目录页未解析出课程详情链接")

    def program_detail(self, page, res):
        name = title_from(page, suffix_re=r"\s*\|\s*The University of Sheffield.*$")
        if not name:
            res.note("未解析出课程名称")
            return
        p = ProgramData(name_en=name, level="UG" if "/undergraduate/" in page.url else "PGT",
                        url=page.url, entry_year=_entry_year(page.url, self.entry_year))
        p.duration = _duration(page)
        p.dept = _dept(page)
        p.entry_req_text = section_text(page, r"Entry requirements", limit=800)
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        self._modules(page, p)
        if _fee_lookup(page):
            p.notes.append("学费由 courseFees JS lookup 提供，静态页金额置 None")
        res.programs.append(p)

    def _modules(self, page, p):
        area = section_text(page, r"Modules", limit=7000)
        if not area:
            return
        for line in [norm_ws(x) for x in area.splitlines() if norm_ws(x)]:
            if 6 <= len(line) <= 140 and not re.search(r"module|optional|core|fees|apply|year ", line, re.I):
                p.modules.append(ModuleRef(name=line))

    def term_dates(self, page, res):
        if re.search(r"/about/dates/?$", page.url):
            for url, title, _ in find_links(page, r"/about/dates/(?:current-and-future-semester|past|non-standard-semesters)"):
                res.discovered.append(DiscoveredPage(
                    url=url, category="term_dates", title=title or None))
            if not res.discovered:
                res.note("dates hub 未解析到子页面")
            return
        year = None
        for node in page.soup.find_all(["h2", "h3", "dt", "tr"]):
            text = norm_ws(node.get_text(" ", strip=True))
            y = re.search(r"\b(20\d{2})-(\d{2})\b", text)
            if y:
                year = f"{y.group(1)}/{y.group(2)}"
            start, end = _row_dates(node) if node.name == "tr" else date_range(text)
            if year and start:
                name = "Semester date" if node.name == "tr" else re.sub(r"\d{1,2}.*$", "", text).strip(" :-")
                res.calendar.append(CalendarData(year, event_type(name, start), name or "Semester date", start, end))
        if not res.calendar:
            res.note("Sheffield term dates 未解析出日期")

    def deadlines(self, page, res):
        for tr in page.soup.find_all("tr"):
            cells = [norm_ws(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
            if len(cells) < 2:
                continue
            d = date_loose(cells[0])
            if not d:
                continue
            low = cells[1].lower()
            for phrases, dtype, aud_rule in DEADLINE_KEYWORDS:
                if any(ph in low for ph in phrases):
                    aud = (("international" if "visa" in low else "all")
                           if aud_rule == "visa_check" else aud_rule)
                    res.deadlines.append(DeadlineData(
                        aud, dtype, d + " 23:59:00", self.entry_year, cells[1]))
                    break
        if not res.deadlines:
            res.note("Sheffield deadlines 未解析出截止日期")

    def fees(self, page, res):
        res.info("Sheffield fees lookup 作为参考页抓取")

    def language_req(self, page, res):
        overall, minimum = ielts(page.txt)
        if overall is None:
            res.note("未解析出 IELTS 数字")
        elif minimum is None:
            res.info(f"IELTS overall {overall}")
        else:
            res.info(f"IELTS overall {overall}, minimum {minimum}")

    def china_page(self, page, res):
        keyword_check(res, page, r"China", "Sheffield 中国专页")

    def faculty_list(self, page, res):
        if not re.search(FACULTY_RE, page.txt):
            res.note("未匹配到 Sheffield Faculty 名称")

    def ug_admissions(self, page, res):
        res.info("Sheffield UG 招生页作为参考页抓取")

    def pg_admissions(self, page, res):
        res.info("Sheffield PGT 招生页作为参考页抓取")


def _entry_year(url, default):
    m = re.search(r"/(20\d{2})/", url)
    return m.group(1) if m else default


def _duration(page):
    node = page.soup.select_one(".pgduration, #duration-list li, .duration-list-item")
    return norm_ws(node.get_text(" ", strip=True)) if node else None


def _dept(page):
    m = re.search(r"\b(School of [A-Z][A-Za-z &,\-]{3,80}|Management School|Information School)\b", page.txt)
    return norm_ws(m.group(1)) if m else None


def _fee_lookup(page):
    html = page.html.decode("utf-8", "ignore") if isinstance(page.html, bytes) else page.html
    return re.search(r'"courseFees"\s*:', html) is not None


def _row_dates(tr):
    headers = [norm_ws(th.get_text(" ", strip=True)) for th in tr.find_parent("table").find_all("th")]
    cells = [norm_ws(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
    try:
        return date_loose(cells[headers.index("Start date")]), date_loose(cells[headers.index("End date")])
    except (ValueError, IndexError, AttributeError):
        return None, None
