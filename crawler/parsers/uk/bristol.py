"""University of Bristol parser."""
import re
from urllib.parse import urlparse

from parsers.base import BaseParser, CalendarData, DeadlineData, DiscoveredPage, ModuleRef, ProgramData, norm_ws, parse_date
from parsers.uk.common import date_range, event_type, facts, fee_near, ielts, known_name, pick, section_text, title_from

PG_AWARDS = r"MSc|MA|LLM|MRes|MEd|PGDip|PGCert|MBA|MPH"


class Bristol(BaseParser):
    uni_code = "bristol"

    def program_catalog(self, page, res):
        for a in page.soup.find_all("a", href=True):
            url = page.abs(a["href"])
            cat = _target(url)
            if cat:
                res.discovered.append(DiscoveredPage(
                    url=url, category=cat, title=_catalog_title(a.get_text(" ", strip=True))))
        _dedupe(res.discovered)
        if not res.discovered:
            res.note("未解析出 Bristol 课程/学科链接")

    def program_detail(self, page, res):
        name = title_from(page, suffix_re=r"\s*\|\s*Study at Bristol.*$")
        if not name:
            res.note("未解析出课程标题")
            return
        f = facts(page)
        p = ProgramData(name_en=name, level=_level(page.url, name), url=page.url,
                        entry_year=_entry_year(page.url, page.txt, self.entry_year))
        p.ucas_code = pick(f, "ucas code", "ucas course code") or page.re(
            r"UCAS(?: course)? code\s*\n?\s*([A-Z0-9]{4,5})", flags=re.I)
        p.duration = pick(f, "duration", "course duration", "study mode")
        p.faculty = known_name(self.conf.faculties, pick(f, "faculty") or page.txt)
        p.dept = pick(f, "school", "department")
        p.tuition_home = fee_near(page.txt, ("Home: full-time", "Home:"))
        p.tuition_intl = fee_near(page.txt, ("Overseas: full-time", "Overseas:"))
        p.fee_year_label = page.re(r"(20\d{2}/\d{2})")
        p.entry_req_text = (pick(f, "entry requirements", "academic requirements")
                            or section_text(page, r"Entry requirements?", limit=700))
        # 实测措辞（2026-07）：'profile level B' / 'Profile level G'
        m = re.search(r"\bProfile\s+(?:level\s+)?([A-H])\b", page.txt, re.I)
        p.language_band = f"profile-{m.group(1).lower()}" if m else None
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        self._deadlines(page, p)
        self._modules(page, p)
        if p.tuition_intl is None and p.level == "PGT":
            p.notes.append("未解析出国际学费")
        res.programs.append(p)

    def _deadlines(self, page, p):
        for raw in re.findall(r"(?:International|Overseas|Home|Application deadline)"
                              r"[:\s\n-]+(\d{1,2} \w+ 20\d{2})", page.txt, re.I):
            d = parse_date(raw)
            if d:
                p.deadlines.append(DeadlineData(
                    "all", "application", d + " 23:59:00", p.entry_year, "课程页申请截止"))

    def _modules(self, page, p):
        area = section_text(page, r"(?:Programme|Course) structure|Units|Modules", limit=5000)
        if not area:
            return
        for name, _credits in re.findall(r"([A-Z][A-Za-z0-9 ,:&'()/.-]{5,120}?)\s+[–-]\s+\d{1,3}\s+credits?", area):
            p.modules.append(ModuleRef(name=norm_ws(name), module_type="core"))

    def term_dates(self, page, res):
        for table in page.soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            years = [_year(c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"])]
            for tr in rows[1:]:
                cells = [norm_ws(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
                for idx, raw in enumerate(cells[1:], start=1):
                    start, end = date_range(raw)
                    if idx < len(years) and years[idx] and start:
                        res.calendar.append(CalendarData(
                            years[idx], event_type(cells[0], start), cells[0], start, end))
        if not res.calendar:
            res.note("Bristol term dates 未解析出日期")

    def ug_admissions(self, page, res):
        for raw in re.findall(r"\b\d{1,2} \w+ 20\d{2}\b", page.txt):
            d = parse_date(raw)
            if d and "UCAS" in page.txt[max(0, page.txt.find(raw) - 160):page.txt.find(raw) + 160]:
                res.deadlines.append(DeadlineData(
                    "all", "equal_consideration", d + " 18:00:00", self.entry_year, "UCAS 日期"))

    def pg_admissions(self, page, res):
        res.info("Bristol PGT 截止日期在课程页解析")

    def language_req(self, page, res):
        if not re.search(r"\bProfile\s+[A-H]\b", page.txt, re.I):
            res.note("未解析到 Profile A-H")

    def china_page(self, page, res):
        if "China" not in page.txt:
            res.note("China 页面未匹配到 China 关键词")

    def faculty_list(self, page, res):
        if not known_name(self.conf.faculties, page.txt):
            res.note("未匹配到 Bristol Faculty 名称")


def _target(url):
    path = urlparse(url).path.rstrip("/")
    if re.search(r"/study/postgraduate/taught/[a-z0-9-]+$", path) and not path.endswith("/study-online"):
        return "program_detail"
    m = re.search(r"/study/undergraduate/20\d{2}/([^/]+)(?:/([^/]+))?$", path)
    if not m:
        return None
    return "program_detail" if m.group(2) else "program_catalog"


def _catalog_title(text):
    text = norm_ws(text)
    text = re.sub(r"^Taught postgraduate programme\s+", "", text)
    text = re.split(r"\s+(?:Find out|Modes of study|Awards available)\b", text, 1)[0]
    return text[:252].rstrip() + "..." if len(text) > 255 else (text or None)


def _level(url, name):
    if "/undergraduate/" in url:
        return "UG"
    return "PGT" if re.search(rf"\b(?:{PG_AWARDS})\b", name) else "PGR"


def _entry_year(url, txt, default):
    m = re.search(r"/study/undergraduate/(20\d{2})/", url)
    return m.group(1) if m else default


def _year(text):
    m = re.search(r"(20\d{2})/(\d{2})", text)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def _dedupe(items):
    seen = set()
    items[:] = [d for d in items if not (d.url in seen or seen.add(d.url))]
