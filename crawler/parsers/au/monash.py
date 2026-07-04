"""莫纳什大学解析器（handbook.monash.edu = CourseLoop/Next.js，实测 2026-07）。

页面特点：
- 列表/搜索页纯 SPA 零内嵌、ES API 有网关令牌——枚举走 sitemap
  （索引 → 28 子图，按 /{entry_year}/ 过滤出 courses/units 详情 URL）；
- 详情页 SSR，__NEXT_DATA__ 内嵌完整 JSON（props.pageProps.pageContent）：
  title / code / credit_points / school(=院系归属) / aqf_level /
  unit_offering(校区+学期) / full_time_duration——名单+归属一层采齐；
- aos（Areas of Study）页不采：非专业非课程，辅导镜头用不上。
"""
import json
import re

from parsers.base import BaseParser
from parsers.models import DiscoveredPage, ModuleData, ProgramData
from config.codes import Category, UniCode

def _aqf_to_level(label):
    """AQF 等级标签 → UG/PGT/PGR。Level ≤8 的本科侧 → UG，
    Graduate Cert/Dip 与 Masters → PGT，Level 10 → PGR。"""
    if not label:
        return None
    m = re.search(r"Level\s+(\d+)", label)
    if not m:
        return None
    n = int(m.group(1))
    if n >= 10:
        return "PGR"
    if n == 9 or "graduate" in label.lower():
        return "PGT"
    return "UG"


def _text(page):
    """fetcher 给解析器的 body 是 bytes（仅 soup 会自动解码），正则前先转 str。"""
    h = page.html
    return h.decode("utf-8", "replace") if isinstance(h, bytes) else h


class Monash(BaseParser):
    uni_code = UniCode.MONASH

    # ---------------- NEXT_DATA 公共提取 ----------------
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

    @staticmethod
    def _ref_value(v):
        """CourseLoop 引用字段形如 {'value': 'Faculty of IT', ...}。"""
        return v.get("value") if isinstance(v, dict) else v

    # ---------------- sitemap 枚举 ----------------
    def program_catalog(self, page, res):
        locs = re.findall(r"<loc>([^<]+)</loc>", page.html)
        if not locs:
            res.note("sitemap 未解析出 <loc> 条目")
            return
        y = self.entry_year
        if "<sitemapindex" in page.html:
            for u in locs:
                res.discovered.append(DiscoveredPage(
                    url=u, category=Category.PROGRAM_CATALOG, title="子 sitemap"))
            return
        for u in locs:
            m = re.match(rf"https://handbook\.monash\.edu/{y}/(courses|units)/([A-Za-z0-9]+)$", u)
            if not m:
                continue
            kind, code = m.groups()
            res.discovered.append(DiscoveredPage(
                url=u,
                category=(Category.PROGRAM_DETAIL if kind == "courses"
                          else Category.MODULE_CATALOG),
                title=code.upper()))

    # ---------------- 专业页（course）----------------
    def program_detail(self, page, res):
        pc = self._page_content(page, res)
        if not pc:
            return
        name = pc.get("title")
        level = _aqf_to_level((pc.get("aqf_level") or {}).get("label"))
        if not name or not level:
            res.note(f"course 页缺 title/aqf_level: {pc.get('code')}")
            return
        p = ProgramData(name_en=name, level=level, url=page.url,
                        entry_year=self.entry_year, currency="AUD")
        p.faculty = self._ref_value(pc.get("school"))
        p.campus = pc.get("location") or None
        ft = pc.get("full_time_duration") or []
        if ft and ft[0].get("duration_number"):
            p.duration = f"{ft[0]['duration_number']} years full-time"
        if pc.get("code"):
            p.notes.append(f"handbook code: {pc['code']}")
        res.programs.append(p)

    # ---------------- 课程页（unit）----------------
    def module_catalog(self, page, res):
        pc = self._page_content(page, res)
        if not pc:
            return
        name, code = pc.get("title"), pc.get("code")
        if not name or not code:
            res.note("unit 页缺 title/code")
            return
        periods = []
        for off in pc.get("unit_offering") or []:
            per = self._ref_value(off.get("teaching_period")) or ""
            loc = self._ref_value(off.get("location")) or ""
            if per and f"{per}" not in periods:
                periods.append(per if not loc else f"{per} ({loc})")
        credits = None
        if str(pc.get("credit_points", "")).isdigit():
            credits = int(pc["credit_points"])
        lvl = re.match(r"[A-Za-z]+(\d)", code)
        res.modules.append(ModuleData(
            name_en=name, url=page.url, entry_year=self.entry_year,
            code=code.upper(), dept=self._ref_value(pc.get("school")),
            credits=credits, level=f"L{lvl.group(1)}" if lvl else None,
            semester="; ".join(periods)[:120] or None))
