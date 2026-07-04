"""华威大学解析器（选择器实测 2026-07）。

注意：站点限流严（实测 429，域限速已放宽到 8s）；语言要求为
Band A-C 分级制；课程列表部分 JS 渲染。
"""
import re

from parsers.base import BaseParser
from parsers.page import norm_ws
from parsers.models import (CalendarData, DeadlineData, DiscoveredPage,
                            ModuleData, ProgramData)
from parsers.uk.common import (date_range, event_type, band, fee_near, find_links, first, ielts,
                               keyword_check, known_name, section_text, standard_deadlines, title_from)
from config.codes import Category, EventType, UniCode

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

    # ---------------- 官方课程目录（courses.warwick.ac.uk，全开放但慢）----------------
    # 实测 2026-07-05：无反爬（"429" 系当年并发过猛的误判）。表单页 departments
    # 下拉（~164 系代码+全名）→ 搜索页 ?departments=<code>&academicYears=2025
    # &page=N（0 起，每页 50，页满则懒发现下一页）。行 = 代码链接(CS130-15)+
    # 课名+系缩写；系全名经 uaDept 附加参数沿链传递（站点容忍未知参数）。
    CATALOGUE = "https://courses.warwick.ac.uk/modules"
    CATALOGUE_YEAR = "2025"       # 25/26 教学年（select 值）
    PAGE_SIZE = 50

    def module_catalog(self, page, res):
        from urllib.parse import parse_qs, quote, urlsplit
        q = parse_qs(urlsplit(page.url).query)
        if "departments" not in q:        # 表单页：枚举系下拉
            sel = page.soup.select_one('select[name="departments"]')
            for o in (sel.select("option") if sel else []):
                code = str(o.get("value") or "").strip()
                name = o.get_text(" ", strip=True)
                if not code:
                    continue
                res.discovered.append(DiscoveredPage(
                    url=(f"{self.CATALOGUE}?departments={code}"
                         f"&academicYears={self.CATALOGUE_YEAR}&page=0"
                         f"&uaDept={quote(name)}"),
                    category=Category.MODULE_CATALOG,
                    title=f"{name} 课程名单"))
            if not res.discovered:
                res.note("目录表单页未枚举到 departments 下拉")
            return
        dept = (q.get("uaDept") or [None])[0]
        seen = set()
        for a in page.soup.select(f'a[href^="/modules/{self.CATALOGUE_YEAR}/"]'):
            slug = page.abs(a["href"]).rstrip("/").rsplit("/", 1)[-1]   # CS130-15
            m = re.fullmatch(r"([A-Z]{2,4}\d{2,4}[A-Z]?)-(\d+(?:\.\d+)?)", slug)
            if not m or slug in seen:
                continue
            cell = a.find_parent("td")
            nxt = cell.find_next_sibling("td") if cell else None
            name = norm_ws(nxt.get_text(" ", strip=True)) if nxt else ""
            if not name:
                continue
            seen.add(slug)
            credits = float(m.group(2))
            res.modules.append(ModuleData(
                name_en=name, url=page.abs(a["href"]), entry_year=self.entry_year,
                code=m.group(1), dept=dept,
                credits=int(credits) if credits == int(credits) else None))
        if len(seen) >= self.PAGE_SIZE:   # 页满 → 懒发现下一页
            nxt_page = int((q.get("page") or ["0"])[0]) + 1
            from urllib.parse import quote as _q
            res.discovered.append(DiscoveredPage(
                url=(f"{self.CATALOGUE}?departments={q['departments'][0]}"
                     f"&academicYears={self.CATALOGUE_YEAR}&page={nxt_page}"
                     f"&uaDept={_q(dept or '')}"),
                category=Category.MODULE_CATALOG,
                title=f"{dept} 课程名单 p{nxt_page}"))
        if not res.modules:
            res.info("该系本学年无课程行（小单位常见）")

    def term_dates(self, page, res):
        if "examination_dates" in page.url:
            return self._exam_dates(page, res)
        return self._term_dates(page, res)

    def _exam_dates(self, page, res):
        """考试期页（实测 2026-07-05）：'2025/26 Exam Dates' 标题后跟表格，
        行 = 考试窗口名（December 2025 / Summer 2026 / Resits...）+ 日期区间
        （带星期前缀和序数词后缀，date_range 已兼容）。表格语义即考试期。"""
        for table in page.soup.find_all("table"):
            cap = table.find("caption")
            m = re.search(r"(20\d{2})/(\d{2}) Exam Dates",
                          cap.get_text(" ", strip=True) if cap else "")
            if not m:
                continue
            ym = f"{m.group(1)}/{m.group(2)}"
            for tr in table.find_all("tr"):
                cells = [norm_ws(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                if len(cells) < 2 or not cells[0]:
                    continue
                start, end = date_range(cells[-1])
                if not start:
                    continue
                etype = (EventType.RESIT_PERIOD if "resit" in cells[0].lower()
                         else EventType.EXAM_PERIOD)
                label = norm_ws(re.sub(r"\s*\[\d\]", "", cells[0]))   # 剥脚注符
                res.calendar.append(CalendarData(ym, etype, f"{label} 考试期", start, end))
        if not res.calendar:
            res.note("华威考试期页未解析出日期区间")

    def _term_dates(self, page, res):
        """版式（实测 2026-07-05）：学年标题行（2025/2026）后跟
        「标签行 + 日期区间行」成对（Campus Arrivals/Welcome Week/
        Autumn|Spring|Summer Term），三个学年连排。"""
        ym = label = None
        for raw in page.txt.split("\n"):
            line = raw.strip()
            if not line:
                continue
            m = re.fullmatch(r"(20\d{2})/(20\d{2})", line)
            if m:
                ym, label = f"{m.group(1)}/{m.group(2)[2:]}", None
                continue
            start, end = date_range(line)
            if ym and label and start:
                res.calendar.append(CalendarData(
                    ym, event_type(label, start), label, start, end))
                label = None
            elif len(line) < 40 and not re.search(r"\d", line):
                label = line
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
