"""澳国立（ANU）解析器 —— 澳洲第五所（2026-07-05 调研）。

数据拓扑（自研目录站 programsandcourses.anu.edu.au，非 CourseLoop）：
- **公开 JSON API 枚举**：/data/CourseSearch/GetCourses?SelectedYear=2026
  &PageSize=2000&PageIndex=N（2026 = 3,013 门，两页扫完；TotalCount 字段
  是坏的，翻页翻到空为准）；专业走 /data/ProgramSearch/GetPrograms
  {UnderGraduate,PostGraduate}（96 + 199 个）。
- 详情页服务端渲染，元数据是规整键值列表（li: label|value）：
  Code / Unit Value / **Offered by(学院) / ANU College(学部)** ——两级归属齐。
- 校历 = www.anu.edu.au/directories/university-calendar?year=YYYY：
  表格行「DD Mon 事件名 | 年份」，含 Semester begins/ends 与
  examination period（成对 begin/end 行，解析时并成区间）。
- 反爬：无（6 并发全 200）。
"""
import json
import re

from parsers.base import BaseParser
from parsers.models import CalendarData, DiscoveredPage, ModuleData, ProgramData
from parsers.page import norm_ws
from parsers.uk.common import date_loose, event_type
from config.codes import Category, UniCode

SITE = "https://programsandcourses.anu.edu.au"
API_PAGE_SIZE = 2000


class ANU(BaseParser):
    uni_code = UniCode.ANU

    # ---------------- API 枚举（JSON 响应按普通页面抓，解析器自己 loads）----
    def program_catalog(self, page, res):
        try:
            data = json.loads(_text(page))
        except json.JSONDecodeError:
            res.note("API 响应不是 JSON（结构变了或被挑战页替换）")
            return
        items = data.get("Items") or []
        y = self.entry_year
        if "CourseSearch/GetCourses" in page.url:
            for it in items:
                code = (it.get("CourseCode") or "").strip()
                if code:
                    res.discovered.append(DiscoveredPage(
                        url=f"{SITE}/{y}/course/{code}",
                        category=Category.MODULE_CATALOG,
                        title=norm_ws(it.get("Name") or code)))
            if len(items) == API_PAGE_SIZE:      # 页满 → 懒发现下一页
                m = re.search(r"PageIndex=(\d+)", page.url)
                nxt = int(m.group(1)) + 1 if m else 1
                res.discovered.append(DiscoveredPage(
                    url=re.sub(r"PageIndex=\d+", f"PageIndex={nxt}", page.url),
                    category=Category.PROGRAM_CATALOG, title=f"课程 API p{nxt}"))
            if not items and "PageIndex=0" in page.url:
                res.note("课程 API 返回空（年份参数或接口变了？）")
            return
        if "ProgramSearch/GetPrograms" in page.url:
            level = "UG" if "UnderGraduate" in page.url else "PGT"
            for it in items:
                plan = (it.get("AcademicPlanCode") or "").strip()
                if plan:
                    res.discovered.append(DiscoveredPage(
                        url=f"{SITE}/{y}/program/{plan}?uaLevel={level}",
                        category=Category.PROGRAM_DETAIL,
                        title=norm_ws(it.get("ProgramName") or plan)))
            if not items:
                res.info("专业 API 返回空")

    # ---------------- 课程详情（course = 英式 module）----------------
    def module_catalog(self, page, res):
        meta = _meta_list(page)
        name = _page_title(page)
        code = meta.get("Code")
        if not name or not code:
            res.note("course 页缺标题/Code")
            return
        units = None
        m = re.search(r"(\d+)", meta.get("Unit Value") or "")
        if m:
            units = int(m.group(1))
        lvl = re.search(r"[A-Za-z]+(\d)", code)
        res.modules.append(ModuleData(
            name_en=name, url=page.url.split("?")[0], entry_year=self.entry_year,
            code=code.upper(), dept=meta.get("Offered by"),
            credits=units, level=f"L{lvl.group(1)}" if lvl else None))

    # ---------------- 专业详情 ----------------
    def program_detail(self, page, res):
        from urllib.parse import parse_qs, urlsplit
        meta = _meta_list(page)
        name = _page_title(page)
        if not name:
            res.note("program 页缺标题")
            return
        level = (parse_qs(urlsplit(page.url).query).get("uaLevel") or ["PGT"])[0]
        plan = meta.get("Academic plan")
        p = ProgramData(
            name_en=f"{plan} - {name}" if plan else name,   # 同名学位按代码保唯一
            level=level, url=page.url.split("?")[0], entry_year=self.entry_year)
        p.dept = meta.get("Offered by")
        # 专业页元数据表常无学院行，正文有独立的学院徽标行（实测 2026-07-05）
        p.faculty = meta.get("ANU College")
        if not p.faculty:
            m2 = re.search(r"ANU College of [A-Z][A-Za-z,&\- ]{3,50}", page.txt)
            p.faculty = norm_ws(m2.group(0)) if m2 else None
        p.duration = meta.get("Length")
        res.programs.append(p)

    # ---------------- 校历 ----------------
    def term_dates(self, page, res):
        """university-calendar（实测 2026-07-05）：表格行
        「DD Mon 事件名 | 年份」；examination period 成对 begin/end 并成区间。"""
        events = []          # (label, iso_date)
        for tr in page.soup.select("table tr"):
            cells = [norm_ws(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
            if len(cells) < 2 or not re.fullmatch(r"20\d{2}", cells[-1]):
                continue
            m = re.match(r"(\d{1,2} \w{3,9})\s+(.{3,90})$", cells[0])
            if not m:
                continue
            d = date_loose(f"{m.group(1)} {cells[-1]}")
            if d:
                events.append((norm_ws(m.group(2)), d, cells[-1]))
        merged: dict[tuple, tuple] = {}
        for label, d, year in events:
            base = re.sub(r"\s*(ends|period ends)$", "", label)
            key = (year, base)
            if label != base or label.endswith("ends"):
                if key in merged:
                    merged[key] = (merged[key][0], d)
                continue
            merged[key] = (d, d)
        for (year, label), (start, end) in merged.items():
            res.calendar.append(CalendarData(
                year, event_type(label, start), label, start, max(end, start)))
        if not res.calendar:
            res.note("ANU university calendar 未解析出日期")


def _text(page):
    h = page.html
    return h.decode("utf-8", "ignore") if isinstance(h, bytes) else h


def _page_title(page):
    t = page.soup.title.get_text(" ", strip=True) if page.soup.title else ""
    return norm_ws(re.sub(r"\s*-\s*ANU$", "", t)) or None


def _meta_list(page):
    """键值列表（li 内 label 与 value 两段）→ dict。"""
    out = {}
    for li in page.soup.find_all("li"):
        parts = [norm_ws(x) for x in li.get_text("\n", strip=True).split("\n") if x.strip()]
        if len(parts) == 2 and 2 <= len(parts[0]) <= 24 and parts[0] not in out:
            out[parts[0]] = parts[1]
    return out
