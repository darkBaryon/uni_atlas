"""University of Leeds parser."""
import re
from urllib.parse import urlparse

from parsers.base import BaseParser
from parsers.models import CalendarData, DeadlineData, DiscoveredPage, ModuleRef, ProgramData
from parsers.page import norm_ws, parse_date
from parsers.uk.common import (dedupe_discovered, event_type, facts, fee_near, ielts,
                               keyword_check, known_name, pick, scan_term_lines,
                               section_text, title_from, unwrap_funnelback)
from config import codes

PG_AWARDS = r"MSc|MA|MBA|LLM|MRes|MEd|MPH|PGDip|PGCert|Masters"


class Leeds(BaseParser):
    uni_code = codes.LEEDS

    def program_catalog(self, page, res):
        seen = set()
        for a in page.soup.find_all("a", href=True):
            url = unwrap_funnelback(page.abs(a["href"]))
            if _is_detail(url) and url not in seen:
                seen.add(url)
                res.discovered.append(DiscoveredPage(
                    url=url, category="program_detail",
                    title=norm_ws(a.get_text(" ", strip=True)) or None))
            elif "course-search/" in url and ("start_rank=" in url or "page=" in url):
                res.discovered.append(DiscoveredPage(
                    url=url, category="program_catalog", title="Course search page"))
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

    def term_dates(self, page, res):
        # 学年从行内/上文捕获（原实现硬拼 f"{entry_year}/27"，2027 季会出错）
        scan_term_lines(page, res, CalendarData, r"term|semester|induction|exam")
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


def _level(name, url):
    return "PGT" if "/masters" in url or re.search(rf"\b(?:{PG_AWARDS})\b", name) else "UG"


def _entry_year(url, txt, default):
    m = re.search(r"/(20\d{2})\d{2}/", url)
    return m.group(1) if m else default


def _window(txt, needle, size=220):
    pos = txt.find(needle)
    return norm_ws(txt[max(0, pos - size):pos + size]) if pos >= 0 else ""

