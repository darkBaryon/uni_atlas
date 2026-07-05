"""阿德莱德大学（合并新校 Adelaide University）解析器 —— 澳洲第七所（2026-07-05 调研）。

背景：2026-01 起原阿德莱德大学与南澳大学合并为新 "Adelaide University"
（八大席位由新校继承），课程体系全部重编——**旧 access.adelaide.edu.au
Course Planner 已死（TLS 拒连），只认新站**。

数据拓扑（adelaide.edu.au 单站，服务端渲染）：
- 枚举走 **sitemap.xml**（单张 8,241 loc）：/study/degrees/<slug>/ = 学位
  （524 个）；/study/courses/<code-slug>/ = 课程（5,521 门，slug 即代码
  acct-1001）。
- 课程页元数据 = 文本标签/值行对：Area/Catalogue(代码) / Unit value(学分) /
  Level of study / **Course owner(=学院归属)** / Course coordinator。
- 学位页有 Program code / Duration / Campus，**无归属字段**（合并后学部
  结构未在页面透出，expect 注明）。
- 校历 = /students/manage-study/academic-calendar/：学期节头 +
  标签/日期表格行，日期不带年份（取种子年）。
- 反爬：无。
"""
import re

from parsers.base import BaseParser
from parsers.models import CalendarData, DiscoveredPage, ModuleData, ProgramData
from parsers.page import norm_ws
from parsers.uk.common import date_loose, event_type
from config.codes import Category, UniCode

DEGREE_RE = re.compile(r"https://adelaide\.edu\.au/study/degrees/([a-z0-9-]{8,})/$")
COURSE_RE = re.compile(r"https://adelaide\.edu\.au/study/courses/([a-z]{2,6}-\d{4}[a-z]*)/$")


class Adelaide(BaseParser):
    uni_code = UniCode.ADEL

    # ---------------- sitemap 枚举 ----------------
    def program_catalog(self, page, res):
        html = _text(page)
        locs = re.findall(r"<loc>([^<]+)</loc>", html)
        if not locs:
            res.note("sitemap 未解析出 <loc>")
            return
        for u in locs:
            if COURSE_RE.match(u):
                res.discovered.append(DiscoveredPage(
                    url=u, category=Category.MODULE_CATALOG))
            elif DEGREE_RE.match(u):
                res.discovered.append(DiscoveredPage(
                    url=u, category=Category.PROGRAM_DETAIL))

    # ---------------- 课程页 ----------------
    def module_catalog(self, page, res):
        kv = _line_pairs(page)
        name = _title(page)
        code = norm_ws(kv.get("Area/Catalogue") or "").replace(" ", "")
        if not name or not code:
            res.note("course 页缺标题/Area-Catalogue 代码")
            return
        units = kv.get("Unit value")
        lvl = kv.get("Course level")
        res.modules.append(ModuleData(
            name_en=name, url=page.url, entry_year=self.entry_year,
            code=code.upper(), dept=kv.get("Course owner"),
            credits=int(units) if units and units.isdigit() else None,
            level=f"L{lvl}" if lvl and lvl.isdigit() else None,
            leader=kv.get("Course coordinator")))

    # ---------------- 学位页 ----------------
    def program_detail(self, page, res):
        name = _title(page)
        if name:
            name = re.sub(r"^Study ", "", name)   # 学位页 title 带营销前缀
        if not name:
            res.note("degree 页缺标题")
            return
        kv = _line_pairs(page)
        slug = page.url.rstrip("/").rsplit("/", 1)[-1]
        level = ("UG" if slug.startswith("bachelor") else "PGT")
        code = kv.get("Program code")
        p = ProgramData(
            name_en=f"{code} - {name}" if code else name,
            level=level, url=page.url, entry_year=self.entry_year)
        m = re.search(r"(\d+(?:\.\d+)? year\(s\)[^\n]{0,30})", _text_of(page))
        p.duration = norm_ws(m.group(1)) if m else None
        res.programs.append(p)

    # ---------------- 校历 ----------------
    def term_dates(self, page, res):
        """academic-calendar（实测 2026-07-05）：学期节头（Semester 1）后接
        「事件标签 | 日期」表格行；日期不带年份（用种子年）。"""
        year = self.entry_year
        for table in page.soup.find_all("table"):
            heading = table.find_previous(["h2", "h3", "h4", "caption"])
            sem = None
            if heading:
                m = re.search(r"(Semester [12]|Summer|Winter|Trimester \d|Study Period \d+)",
                              heading.get_text(" ", strip=True))
                sem = m.group(1) if m else None
            for tr in table.find_all("tr"):
                cells = [norm_ws(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
                # 实测列序：日期在前、事件标签在后
                if len(cells) < 2 or not re.search(r"\d{1,2} \w{3}", cells[0]):
                    continue
                label, datecell = cells[1], cells[0]
                dates = re.findall(r"\d{1,2} \w{3,9}", datecell)
                start = date_loose(f"{dates[0]} {year}") if dates else None
                end = date_loose(f"{dates[-1]} {year}") if len(dates) > 1 else start
                if start and label:
                    full = f"{label}（{sem}）" if sem else label
                    res.calendar.append(CalendarData(
                        year, event_type(label, start), full, start, end or start))
        if not res.calendar:
            res.note("academic-calendar 未解析出日期行")


def _text(page):
    h = page.html
    return h.decode("utf-8", "ignore") if isinstance(h, bytes) else h


def _text_of(page):
    return page.txt


def _title(page):
    t = page.soup.title.get_text(" ", strip=True) if page.soup.title else ""
    return norm_ws(re.sub(r"\s*\|\s*Adelaide University$", "", t)) or None


def _line_pairs(page):
    """文本「标签行→值行」提取；跳过 tooltip 噪音行（More info/Close tooltip）。"""
    lines = [norm_ws(x) for x in page.txt.split("\n") if x.strip()]
    lines = [x for x in lines if x not in ("More info", "Close tooltip")]
    out = {}
    labels = {"Area/Catalogue", "Course ID", "Campus", "Level of study",
              "Unit value", "Course owner", "Course coordinator", "Course level",
              "Program code", "Duration", "Study as"}
    for i, line in enumerate(lines[:-1]):
        if line in labels and line not in out:
            out[line] = lines[i + 1]
    return out
