"""King's College London parser."""
import re

from parsers.base import BaseParser, CalendarData, DeadlineData, DiscoveredPage, ProgramData, parse_date
from parsers.uk_common import date_range, event_type, fee_near, find_links, first, ielts, known_name, section_text, title_from

COURSE_RE = r"/study/(?:undergraduate|postgraduate-taught)/courses/(?!course-types-and-study-options/?$)[a-z0-9-]+/?$"


class KCL(BaseParser):
    uni_code = "kcl"

    def program_catalog(self, page, res):
        for url, title, _ in find_links(page, COURSE_RE):
            res.discovered.append(DiscoveredPage(
                url=url, category="program_detail", title=title or None))
        if not res.discovered:
            res.note("KCL 目录页未解析出静态课程链接")

    def program_detail(self, page, res):
        name = title_from(
            page, bad_h1=("King's College London",),
            suffix_re=r"\s*\|\s*King's College London.*$")
        if not name:
            res.note("未解析出课程标题")
            return
        p = ProgramData(name_en=name, level="UG" if "/undergraduate/" in page.url else "PGT",
                        url=page.url, entry_year=self.entry_year)
        p.duration = first(page.txt, r"(?:Duration|Course length|Length)\s*\n([^\n]{2,120})")
        p.ucas_code = page.re(r"UCAS(?: course)? code\s*\n?\s*([A-Z0-9]{4,5})")
        p.campus = first(page.txt, r"(?:Campus|Location|Teaching location)\s*\n([^\n]{2,120})")
        p.tuition_home = fee_near(page.txt, ("home", "uk"))
        p.tuition_intl = fee_near(page.txt, ("international", "overseas"))
        p.entry_req_text = section_text(
            page, r"Entry requirements|Academic requirements",
            r"English language requirements|Fees and funding|Teaching|Apply|Careers",
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
        for raw in re.findall(r"(?:deadline|closing date)[^\n]{0,120}(\d{1,2} \w+ \d{4})",
                              page.txt, re.I):
            d = parse_date(raw)
            if d:
                p.deadlines.append(DeadlineData(
                    "all", "application", d + " 23:59:00", p.entry_year, "课程页申请截止"))

    def term_dates(self, page, res):
        year = first(page.txt, r"(20\d{2})\s*/\s*(\d{2})") or "2025/26"
        for line in page.txt.splitlines():
            start, end = date_range(line)
            if start and re.search(r"welcome|semester|exam|teaching|holiday", line, re.I):
                name = re.sub(r"\d{1,2}.*$", "", line).strip(" :-") or "Term date"
                res.calendar.append(CalendarData(year, event_type(name, start), name, start, end))
        if not res.calendar:
            res.note("KCL 校历页未解析出日期区间")

    def ug_admissions(self, page, res):
        self._admission_page(page, res, "UG")

    def pg_admissions(self, page, res):
        self._admission_page(page, res, "PGT")

    def _admission_page(self, page, res, level):
        if "deadline" not in page.txt.lower() and "UCAS" not in page.txt:
            res.note(f"KCL {level} 招生页未解析出明确截止日期")

    def language_req(self, page, res):
        if not re.search(r"\bBand\s+[A-E]\b", page.txt, re.I):
            res.note("未解析到 Band A-E")

    def china_page(self, page, res):
        if not re.search(r"China|East Asia", page.txt, re.I):
            res.note("未匹配到 China/East Asia 关键词")

    def faculty_list(self, page, res):
        if not known_name(self.conf.faculties, page.txt):
            res.note("未匹配到 KCL Faculty 名称")


def _band(txt):
    m = re.search(r"\bBand\s+([A-E])\b", txt, re.I)
    return f"band-{m.group(1).upper()}" if m else None
