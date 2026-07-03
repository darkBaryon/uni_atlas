"""University of Birmingham parser."""
import re

from parsers.base import BaseParser, CalendarData, DiscoveredPage, ModuleRef, ProgramData, norm_ws
from parsers.uk.common import date_range, event_type, fee_near, find_links, ielts, section_text, title_from

COURSE_RE = r"/study/(?:undergraduate|postgraduate)/subjects/.+-courses/[^/?#]+/?$"
COLLEGE_RE = r"College of (?:Arts and Law|Engineering and Physical Sciences|Life and Environmental Sciences|Medicine and Health|Social Sciences)"


class BirminghamParser(BaseParser):
    uni_code = "bham"

    def program_catalog(self, page, res):
        for url, title, _ in find_links(page, COURSE_RE):
            if "/dubai/" not in url:
                res.discovered.append(DiscoveredPage(
                    url=url, category="program_detail", title=title or None))
        if not res.discovered:
            res.note("Birmingham 目录页未解析出课程详情链接")

    def program_detail(self, page, res):
        name = title_from(page, suffix_re=r"\s*-\s*University of Birmingham$")
        if not name:
            res.note("未解析出课程名称")
            return
        p = ProgramData(name_en=name, level="UG" if "/undergraduate/" in page.url else "PGT",
                        url=page.url, entry_year=_entry_year(page, self.entry_year))
        tiles = _tiles(page)
        p.ucas_code = tiles.get("UCAS code")
        p.campus = tiles.get("Campus")
        p.duration = tiles.get("Duration")
        p.entry_req_text = tiles.get("Entry requirements") or section_text(page, r"Entry requirements", limit=700)
        p.faculty = self.canon_faculty(page.txt, COLLEGE_RE)
        p.dept = _dept(page)
        p.tuition_home = fee_near(" ".join(tiles.values()) + "\n" + page.txt, ("UK/Ireland", "Home", "UK"))
        p.tuition_intl = fee_near(page.txt, ("International", "Overseas"))
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        self._modules(page, p)
        if p.tuition_intl is None:
            p.notes.append("静态页未稳定暴露国际学费")
        res.programs.append(p)

    def _modules(self, page, p):
        root = page.soup.find(id=re.compile("module", re.I))
        if not root:
            return
        for node in root.find_all(["a", "h3", "h4"]):
            title = norm_ws(node.get_text(" ", strip=True))
            if 6 <= len(title) <= 140 and not re.search(r"module information|optional|compulsory|fees|apply", title, re.I):
                p.modules.append(ModuleRef(name=title, url=page.abs(node["href"]) if node.name == "a" and node.get("href") else None))

    def term_dates(self, page, res):
        year = None
        for node in page.soup.find_all(["h2", "h3", "p", "li"]):
            text = norm_ws(node.get_text(" ", strip=True))
            m = re.search(r"\b(20\d{2})/(\d{2})\b", text)
            if node.name in ("h2", "h3") and m:
                year = f"{m.group(1)}/{m.group(2)}"
                continue
            start, end = date_range(text)
            if year and start:
                label = re.sub(r"\d{1,2}.*$", "", text).strip(" :-") or "Term date"
                res.calendar.append(CalendarData(year, event_type(label, start), label, start, end))
        if not res.calendar:
            res.note("Birmingham academic year dates 未解析出日期")

    def ug_admissions(self, page, res):
        res.info("Birmingham UG 招生页作为参考页抓取")

    def pg_admissions(self, page, res):
        res.info("Birmingham PGT 招生页作为参考页抓取")

    def china_page(self, page, res):
        if "China" not in page.txt:
            res.note("China 页面未匹配到 China 关键词")

    def faculty_list(self, page, res):
        if not re.search(COLLEGE_RE, page.txt):
            res.note("未匹配到 Birmingham College 名称")


def _tiles(page):
    out = {}
    for tile in page.soup.select(".course-tile, .course-tile-select"):
        label = tile.select_one(".course-tile__title, .course-tile-select__title")
        if not label:
            continue
        key = norm_ws(label.get_text(" ", strip=True)).rstrip(":")
        val = tile.select_one(".course-tile__value") or tile.select_one("option[selected]")
        text = norm_ws(val.get_text(" ", strip=True)) if val else ""
        if key and text:
            out[key] = text
    return out


def _entry_year(page, default):
    m = re.search(r"\b(20\d{2})\b", page.url)
    return m.group(1) if m else default


def _dept(page):
    m = re.search(r"\b(Birmingham Business School|School of [A-Z][A-Za-z &,\-]{3,80}|Department of [A-Z][A-Za-z &,\-]{3,80})\b", page.txt)
    return norm_ws(m.group(1)) if m else None
