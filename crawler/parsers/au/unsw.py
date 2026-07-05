"""新南威尔士大学（UNSW）解析器 —— 澳洲第四所（2026-07-05 调研）。

数据拓扑（与莫纳什同为 CourseLoop 平台，字段名略异）：
- 官方目录 = www.handbook.unsw.edu.au：列表页 SPA，**枚举走 sitemap**
  （索引 → 26 张子图 ≈6.6 万 URL 含历年；按 /{entry_year}/ 过滤后
  2026 = 5,762 courses(UG 3,260 + PG 2,502) + 962 programs(UG+PGT)；
  research 侧不采——辅导镜头）。
- 详情页 SSR，__NEXT_DATA__ props.pageProps.pageContent：
  title / code / credit_points / **academic_org(学院) /
  parent_academic_org(学部)** ——名单+两级归属一层采齐。
- 反爬：8 并发探测全 200（无 Imperva/WAF），中高档即可。
- 校历 = student.unsw.edu.au/calendar（可抓）：三学期制（T1 二月/T2 六月/
  T3 九月），版式「年份标题 → 标签行 → 日期区间行（不带年份）」，
  自带 Exams T1/T2/T3 与 O-Week，2026+2027 双年。
"""
import json
import re

from parsers.base import BaseParser
from parsers.models import CalendarData, DiscoveredPage, ModuleData, ProgramData
from parsers.page import norm_ws
from parsers.uk.common import date_range   # 日期区间提取是全语域通用件
from config.codes import Category, UniCode

HANDBOOK = r"https://www\.handbook\.unsw\.edu\.au"


class UNSW(BaseParser):
    uni_code = UniCode.UNSW

    # ---------------- sitemap 枚举 ----------------
    def program_catalog(self, page, res):
        html = _text(page)
        locs = re.findall(r"<loc>([^<]+)</loc>", html)
        if not locs:
            res.note("sitemap 未解析出 <loc> 条目")
            return
        y = self.entry_year
        if "<sitemapindex" in html:
            for u in locs:
                res.discovered.append(DiscoveredPage(
                    url=u, category=Category.PROGRAM_CATALOG, title="子 sitemap"))
            return
        for u in locs:
            m = re.match(rf"{HANDBOOK}/(undergraduate|postgraduate)/"
                         rf"(programs|courses)/{y}/([A-Za-z0-9]+)/?$", u)
            if not m:
                continue   # research 侧与历年条目不采
            _side, kind, code = m.groups()
            res.discovered.append(DiscoveredPage(
                url=u,
                category=(Category.PROGRAM_DETAIL if kind == "programs"
                          else Category.MODULE_CATALOG),
                title=code.upper()))

    # ---------------- 专业页（program）----------------
    def program_detail(self, page, res):
        pc = self._page_content(page, res)
        if not pc:
            return
        name, code = pc.get("title"), pc.get("code")
        if not name:
            res.note(f"program 页缺 title: {code}")
            return
        levels = [x.get("value") for x in pc.get("study_level") or []]
        level = "UG" if "ugrd" in levels else "PGT"
        p = ProgramData(
            name_en=f"{code} - {name}" if code else name,   # 同名学位按代码保唯一（同莫纳什）
            level=level, url=page.url, entry_year=self.entry_year)
        p.dept = _ref(pc.get("academic_org"))
        p.faculty = _ref(pc.get("parent_academic_org"))
        if pc.get("duration_ft_min") and pc.get("duration_ft_period"):
            p.duration = f"{pc['duration_ft_min']} {pc['duration_ft_period']}"
        res.programs.append(p)

    # ---------------- 课程页（course = 英式 module）----------------
    def module_catalog(self, page, res):
        pc = self._page_content(page, res)
        if not pc:
            return
        name, code = pc.get("title"), pc.get("code")
        if not name or not code:
            res.note("course 页缺 title/code")
            return
        credits = None
        if str(pc.get("credit_points", "")).isdigit():
            credits = int(pc["credit_points"])
        lvl = re.match(r"[A-Za-z]+(\d)", code)
        res.modules.append(ModuleData(
            name_en=name, url=page.url, entry_year=self.entry_year,
            code=code.upper(), dept=_ref(pc.get("academic_org")),
            credits=credits, level=f"L{lvl.group(1)}" if lvl else None))

    # ---------------- 校历 ----------------
    def term_dates(self, page, res):
        """student.unsw.edu.au/calendar（实测 2026-07-05）：年份标题下跟
        「事件标签行 + 无年份日期区间行」；跨年区间（12 月-1 月）自带年份。"""
        year = label = None
        for raw in _text_lines(page):
            m = re.fullmatch(r"(20\d{2})", raw)
            if m:
                year, label = m.group(1), None
                continue
            if not year:
                continue
            clean = raw.replace(" ", " ")
            has_date = re.search(r"\d{1,2} \w{3,9}( 20\d{2})?\s*(-|–|to)", clean)
            if not has_date:
                if 3 <= len(clean) <= 45 and not re.search(r"\d{1,2} \w+", clean):
                    label = norm_ws(clean)
                continue
            if not label:
                continue
            seg = clean if "20" in clean else re.sub(
                r"(\d{1,2} \w+)\s*(-|–|to)\s*(\d{1,2} \w+)",
                rf"\g<1> {year} \g<2> \g<3> {year}", clean)
            start, end = date_range(seg)
            if start:
                res.calendar.append(CalendarData(
                    year, _event_type_au(label), label, start, end))
            label = None
        if not res.calendar:
            res.note("UNSW calendar 未解析出学期日期")

    # ---------------- CourseLoop 取数 ----------------
    def _page_content(self, page, res):
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                      _text(page), re.S)
        if not m:
            res.note("页面无 __NEXT_DATA__，可能被挑战页替换或结构已变")
            return None
        try:
            pc = (json.loads(m.group(1)).get("props", {}).get("pageProps", {})
                  .get("pageContent"))
        except json.JSONDecodeError:
            res.note("__NEXT_DATA__ JSON 解析失败")
            return None
        if not pc:
            res.note("pageContent 为空（该条目本年可能未开设）")
        return pc


def _ref(v):
    """CourseLoop 引用字段 {'value': 'Faculty of Science', ...} → 值。"""
    if isinstance(v, dict):
        return v.get("value")
    return v or None


def _text(page):
    h = page.html
    return h.decode("utf-8", "ignore") if isinstance(h, bytes) else h


def _text_lines(page):
    return [line.strip() for line in page.txt.split("\n") if line.strip()]


def _event_type_au(label):
    from parsers.uk.common import event_type   # 词典按措辞匹配，UNSW 措辞在集内
    return event_type(label)
