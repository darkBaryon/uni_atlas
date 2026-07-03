"""华威大学解析器（选择器实测 2026-07）。

注意：站点限流严（实测 429，域限速已放宽到 8s）；语言要求为
Band A-C 分级制；课程列表部分 JS 渲染。
"""
import re

from parsers.base import BaseParser
from parsers.models import CalendarData, DeadlineData, DiscoveredPage, ProgramData
from parsers.uk.common import (band, fee_near, find_links, first, ielts,
                               keyword_check, known_name, scan_term_lines,
                               section_text, standard_deadlines, title_from)
from config.codes import Category, UniCode

COURSE_RE = (r"/study/undergraduate/courses-20\d{2}/[a-z0-9-]+/?$|"
             r"/study/postgraduate/courses(?:-20\d{2})?/(?!course-list/?$)[a-z0-9-]+/?$")


class Warwick(BaseParser):
    uni_code = UniCode.WARWICK

    def program_catalog(self, page, res):
        for url, title, _ in find_links(page, COURSE_RE):
            res.discovered.append(DiscoveredPage(
                url=url, category=Category.PROGRAM_DETAIL, title=title or None))
        if not res.discovered:
            res.note("Warwick 目录页未解析出静态课程链接")

    def program_detail(self, page, res):
        name = title_from(page, suffix_re=r"\s*(?:\||-)\s*(?:University of Warwick|Warwick).*$")
        if not name:
            res.note("未解析出课程标题")
            return
        p = ProgramData(name_en=name, url=page.url,
                        entry_year=_entry_year(page.url, self.entry_year),
                        level="UG" if "/undergraduate/" in page.url else "PGT")
        p.ucas_code = page.re(r"UCAS(?: course)? code\s*\n?\s*([A-Z0-9]{4,5})")
        p.duration = first(page.txt, r"(?:Duration|Course length|Length)\s*\n([^\n]{2,120})",
                           r"(\d+(?:\.\d+)?\s+years?\s+(?:full|part)-time)",
                           r"(\d+\s+months?\s+(?:full|part)-time)")
        p.campus = first(page.txt, r"(?:Location|Campus)\s*\n([^\n]{2,120})")
        p.tuition_home = fee_near(page.txt, ("Home fee", "UK fee", "Home:"))
        p.tuition_intl = fee_near(page.txt, ("Overseas fee", "International fee", "Overseas:"))
        p.entry_req_text = section_text(
            page, r"Entry requirements|General entry requirements|Requirements",
            r"English language requirements|Fees and funding|Modules|Careers|Apply",
            500)
        p.faculty = known_name(self.conf.faculties, page.txt)
        p.language_band = band(page.txt, letters="A-C")
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        standard_deadlines(page, p, DeadlineData)
        if p.tuition_intl is None:
            p.notes.append("未解析出国际学费")
        res.programs.append(p)

    def term_dates(self, page, res):
        scan_term_lines(page, res, CalendarData,
                        r"welcome|autumn|spring|summer|term|exam")
        if not res.calendar:
            res.note("Warwick term dates 未解析出日期区间")

    def ug_admissions(self, page, res):
        keyword_check(res, page, r"deadline|UCAS", "Warwick UG 招生页")

    def pg_admissions(self, page, res):
        keyword_check(res, page, r"deadline|UCAS", "Warwick PGT 招生页")

    def language_req(self, page, res):
        keyword_check(res, page, r"\bBand\s+[ABC]\b", "Warwick 语言分级页")

    def china_page(self, page, res):
        for url, title, _ in find_links(page, r"china"):
            res.discovered.append(DiscoveredPage(url=url, category=Category.CHINA_PAGE,
                                                 title=title or "China"))
        if not res.discovered:
            keyword_check(res, page, r"China", "Warwick 国别页")

    def faculty_list(self, page, res):
        if not known_name(self.conf.faculties, page.txt):
            res.note("未匹配到 Warwick Faculty 名称")


def _entry_year(url, default):
    m = re.search(r"/courses-(20\d{2})/", url)
    return m.group(1) if m else default
