"""墨尔本大学解析器（handbook.unimelb.edu.au，选择器实测 2026-07）。

页面特点：
- 官方 Handbook 独立域名，SSR 无 JS 渲染，列表项 search-result-item__* 语义化
  class 极干净；列表行自带名称/代码/级别/校区/时长/学分/开课期——
  名单+链接一层采齐，不进详情页（策略：详情存链接跳官网）；
- 分页走 /search?page=N&types[]=course|subject&year=YYYY；
  /2026/courses?page=N 形式返回空列表，不可用；
- 反爬 Imperva（"Pardon Our Interruption"）：连发 ~6 请求即触发，
  节奏由 melb.yaml domains 控（5s/单并发），挑战页经 CF_MARKERS 退避；
- 校历：主站 Akamai 403 硬挡，term_dates 人工维护，本解析器不写；
- 学分制：points 有 12.5 之类小数，modules.credits 是整型——不存，
  级别/开课期已够辅导定位用。
"""
import re

from parsers.base import BaseParser
from parsers.models import DiscoveredPage, ModuleData, ProgramData
from parsers.page import norm_ws
from config.codes import Category, FetchMethod, UniCode

# 列表行级别旗标 → programs.level
LEVEL_MAP = {
    "undergraduate coursework": "UG",
    "graduate coursework": "PGT",
    "graduate research": "PGR",
    "research": "PGR",
}

# subjects 行 meta-secondary："Undergraduate Level 1, 12.5 credit points"
SUBJ_LEVEL_RE = re.compile(r"(Undergraduate)\s+Level\s+(\d)|(Graduate)\s+coursework", re.I)


class Melbourne(BaseParser):
    uni_code = UniCode.MELB

    # ---------------- 公共：列表项与分页 ----------------
    def _items(self, page):
        """迭代搜索列表项：(url, name, code, flags, metas)。"""
        for a in page.soup.select("a.search-result-item__anchor[href]"):
            name_el = a.select_one(".search-result-item__name h3")
            code_el = a.select_one(".search-result-item__code")
            flags = [norm_ws(f.get_text(" ", strip=True))
                     for f in a.select(".search-result-item__flag")]
            metas = [norm_ws(p.get_text(" ", strip=True))
                     for p in a.select(".search-result-item__meta p")]
            yield (page.abs(a["href"]),
                   norm_ws(name_el.get_text(" ", strip=True)) if name_el else None,
                   norm_ws(code_el.get_text(" ", strip=True)) if code_el else None,
                   flags, metas)

    def _discover_pages(self, page, res, type_, category):
        """只在种子页（URL 不含 page=）展开：以分页导航里真实的 href 为模板、
        只替换页码，构造 2..最大页 的任务——URL 形状（路径/参数名/年份）全部
        来自页面本身，官方改版时跟着页面走；避免每个分页各自重复发现。"""
        if "page=" in page.url:
            return
        hrefs = [a["href"] for a in page.soup.select("nav.pagination a[href]")
                 if re.search(r"[?&]page=\d+", a.get("href", ""))]
        if not hrefs:
            return
        def _page_no(h):
            m = re.search(r"[?&]page=(\d+)", h)
            return int(m.group(1)) if m else 0   # hrefs 已按该正则过滤，兜底给 mypy
        template = max(hrefs, key=_page_no)
        last = _page_no(template)
        for n in range(2, last + 1):
            url = page.abs(re.sub(r"([?&]page=)\d+", rf"\g<1>{n}", template))
            res.discovered.append(DiscoveredPage(
                url=url, category=category, title=f"{type_} 目录第 {n} 页",
                fetch_method=FetchMethod.CDP))   # handbook 挂 Imperva，分页页也走 CDP

    # ---------------- 专业目录（courses，539 个）----------------
    def program_catalog(self, page, res):
        self._discover_pages(page, res, "course", Category.PROGRAM_CATALOG)
        for url, name, code, flags, metas in self._items(page):
            if not name or "/courses/" not in url:
                continue
            level = next((LEVEL_MAP[f.lower()] for f in flags
                          if f.lower() in LEVEL_MAP), None)
            if level is None:
                continue   # Breadth Track 等非学位条目
            p = ProgramData(name_en=name, level=level, url=url,
                            entry_year=self.entry_year, currency="AUD")
            # metas: ['Parkville, On Campus', '36 months full-time ...']
            for m in metas:
                if "campus" in m.lower():
                    p.campus = m
                elif "month" in m.lower() or "year" in m.lower():
                    p.duration = m
            p.notes.append(f"handbook code: {code}")
            res.programs.append(p)
        if not res.programs and "page=" not in page.url:
            res.note("courses 目录页未解析出专业条目，页面结构可能已变")

    # ---------------- 课程目录（subjects ≈6,200 门）----------------
    def module_catalog(self, page, res):
        self._discover_pages(page, res, "subject", Category.MODULE_CATALOG)
        for url, name, code, _flags, metas in self._items(page):
            if not name or not code or "/subjects/" not in url:
                continue
            level = semester = None
            for m in metas:
                if m.lower().startswith("offered"):
                    semester = norm_ws(m[len("Offered"):]).strip(" ,")
                lm = SUBJ_LEVEL_RE.search(m)
                if lm:
                    level = (f"UG L{lm.group(2)}" if lm.group(1) else "PGT")
            res.modules.append(ModuleData(
                name_en=name, url=url, entry_year=self.entry_year,
                code=code, level=level, semester=semester))
        if not res.modules and "page=" not in page.url:
            res.note("subjects 目录页未解析出课程条目，页面结构可能已变")
