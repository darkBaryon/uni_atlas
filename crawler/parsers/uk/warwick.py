"""University of Warwick parser."""
import re

from parsers.base import BaseParser
from parsers.models import CalendarData, DeadlineData, DiscoveredPage, ProgramData
from parsers.page import parse_date
from parsers.uk.common import date_range, event_type, fee_near, find_links, first, ielts, known_name, section_text, title_from

COURSE_RE = (r"/study/undergraduate/courses-20\d{2}/[a-z0-9-]+/?$|"
             r"/study/postgraduate/courses(?:-20\d{2})?/(?!course-list/?$)[a-z0-9-]+/?$")


class Warwick(BaseParser):
    uni_code = "warwick"

    def program_catalog(self, page, res):
        for url, title, _ in find_links(page, COURSE_RE):
            res.discovered.append(DiscoveredPage(
                url=url, category="program_detail", title=title or None))
        if not res.discovered:
            res.note("Warwick 目录页未解析出静态课程链接")

    def program_detail(self, page, res):
        name = title_from(page, suffix_re=r"\s*(?:\||-)\s*(?:University of Warwick|Warwick).*$")
        if not name:
            res.note("未解析出课程标题")
            return
        p = ProgramData(name_en=name, level="UG" if "/undergraduate/" in page.url else "PGT",
                        url=page.url, entry_year=_entry_year(page.url, self.entry_year))
        p.ucas_code = page.re(r"UCAS(?: course)? code\s*\n?\s*([A-Z0-9]{4,5})")
        p.duration = first(page.txt, r"(?:Duration|Course length|Length)\s*\n([^\n]{2,120})",
                           r"(\d+(?:\.\d+)?\s+years?\s+(?:full|part)-time)",
                           r"(\d+\s+months?\s+(?:full|part)-time)")
        p.campus = first(page.txt, r"(?:Location|Campus)\s*\n([^\n]{2,120})")
        p.tuition_home = fee_near(page.txt, ("home", "uk"))
        p.tuition_intl = fee_near(page.txt, ("overseas", "international"))
        p.entry_req_text = section_text(
            page, r"Entry requirements|General entry requirements|Requirements",
            r"English language requirements|Fees and funding|Modules|Careers|Apply",
            500)
        p.faculty = known_name(self.conf.faculties, page.txt)
        p.language_band = _band(page.txt)
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        self._deadlines(page, p)
        if p.tuition_intl is None:
            p.notes.append("未解析出国际学费")
        res.programs.append(p)

    def _deadlines(self, page, p):
        d = page.date(r"UCAS[^\n]{0,120}?(\d{1,2} \w+ \d{4})", flags=re.I)
        if d:
            p.deadlines.append(DeadlineData(
                "all", "equal_consideration", d + " 18:00:00", p.entry_year, "UCAS 常规截止"))
        for raw in re.findall(r"(?:application deadline|closing date)[^\n]{0,120}(\d{1,2} \w+ \d{4})",
                              page.txt, re.I):
            d = parse_date(raw)
            if d:
                p.deadlines.append(DeadlineData(
                    "all", "application", d + " 23:59:00", p.entry_year, "课程页申请截止"))

    def term_dates(self, page, res):
        current = None
        for line in page.txt.splitlines():
            m = re.search(r"(20\d{2})\s*/\s*(\d{2})|(20\d{2})\s*-\s*(\d{2})", line)
            if m:
                current = f"{m.group(1) or m.group(3)}/{m.group(2) or m.group(4)}"
            start, end = date_range(line)
            if current and start and re.search(r"welcome|autumn|spring|summer|term|exam", line, re.I):
                name = re.sub(r"\d{1,2}.*$", "", line).strip(" :-") or "Term date"
                res.calendar.append(CalendarData(current, event_type(name, start), name, start, end))
        if not res.calendar:
            res.note("Warwick term dates 未解析出日期区间")

    def ug_admissions(self, page, res):
        self._admission_page(page, res, "UG")

    def pg_admissions(self, page, res):
        self._admission_page(page, res, "PGT")

    def _admission_page(self, page, res, level):
        if "deadline" not in page.txt.lower() and "UCAS" not in page.txt:
            res.note(f"Warwick {level} 招生页未解析出明确截止日期")

    def language_req(self, page, res):
        if not re.search(r"\bBand\s+[ABC]\b", page.txt, re.I):
            res.note("未解析到 Band A/B/C")

    def china_page(self, page, res):
        for url, title, _ in find_links(page, r"china"):
            res.discovered.append(DiscoveredPage(url=url, category="china_page", title=title or "China"))
        if not res.discovered and "China" not in page.txt:
            res.note("未匹配到 China 链接或关键词")

    def faculty_list(self, page, res):
        if not known_name(self.conf.faculties, page.txt):
            res.note("未匹配到 Warwick Faculty 名称")


def _band(txt):
    m = re.search(r"\bBand\s+([ABC])\b", txt, re.I)
    return f"band-{m.group(1).upper()}" if m else None


def _entry_year(url, default):
    m = re.search(r"/courses-(20\d{2})/", url)
    return m.group(1) if m else default
