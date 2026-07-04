"""悉尼大学解析器（Coveo 枚举 + SSR 详情页，实测 2026-07）。

数据源与流程：
- 官方目录由 Coveo 搜索驱动；从 clientlib 提出 org+apiKey（公开客户端令牌），
  Coveo REST 支持 GET（access_token 入 query）→ 查询 URL 当种子页，解析 JSON。
- program_catalog 种子 = Coveo Courses 源查询：结果字段够全（名称/studylevel/
  fieldofstudy/学制），**直接建 ProgramData**，并按 totalCount 分页（发现下一页
  Coveo URL）。不抓专业详情页。
- module_catalog 有两形态，按 URL host 分流：
  * Coveo 域（org.coveo.com）= Units 源枚举 JSON → 发现 /units/{code}/{session}
    SSR 详情页任务 + 分页；
  * www.sydney.edu.au/units/ = SSR 详情页 → 解析 ModuleData（h1=代码:全名、
    Credit points、School of X 尽力取）。
- 学院：专业走 fieldofstudy→faculty_alias（100%）；课程学院未进索引，仅正文
  "School of X Student Portal" 链接可 best-effort 取，取不到留空。
"""
import json
import re
from urllib.parse import parse_qs, urlsplit, urlunsplit, urlencode

from parsers.base import BaseParser
from parsers.models import DiscoveredPage, ModuleData, ProgramData
from parsers.page import norm_ws
from config.codes import Category, UniCode

COVEO_HOST = "org.coveo.com"
PAGE_SIZE = 200

# usyd_courses_studylevel → programs.level
LEVEL_MAP = {"uc": "UG", "pc": "PGT", "pr": "PGR"}


def _text(page):
    h = page.html
    return h.decode("utf-8", "replace") if isinstance(h, bytes) else h


def _next_coveo_urls(url, total):
    """按 totalCount 生成 firstResult=200,400,… 的下一页 Coveo URL（只在首页调用）。"""
    parts = urlsplit(url)
    q = parse_qs(parts.query)
    if int(q.get("firstResult", ["0"])[0]) != 0:
        return
    size = int(q.get("numberOfResults", [str(PAGE_SIZE)])[0])
    for first in range(size, total, size):
        q2 = {k: v[0] for k, v in q.items()}
        q2["firstResult"] = first
        yield urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q2), ""))


class Sydney(BaseParser):
    uni_code = UniCode.SYDNEY

    # ---------------- 专业：Coveo Courses 源 ----------------
    def program_catalog(self, page, res):
        try:
            data = json.loads(_text(page))
        except json.JSONDecodeError:
            res.note("program_catalog 非 JSON（Coveo 响应异常）")
            return
        for r in data.get("results", []):
            raw = r.get("raw", {})
            name = norm_ws(r.get("title") or "")
            url = r.get("clickUri")
            if not name or not url:
                continue
            lvl = (raw.get("usyd_courses_studylevel") or [None])
            level = LEVEL_MAP.get(lvl[0] if isinstance(lvl, list) else lvl)
            if not level:
                continue
            p = ProgramData(name_en=name, level=level, url=url,
                            entry_year=self.entry_year, currency="AUD")
            # fieldofstudy 是 slug 列表，取首个能映射到官方学院的
            for fos in (raw.get("usyd_courses_fieldofstudy") or []):
                if fos in self.conf.faculty_alias:
                    p.faculty = fos
                    break
            dur = raw.get("usyd_courses_courseduration")
            if dur:
                p.duration = norm_ws(dur)
            res.programs.append(p)
        for u in _next_coveo_urls(page.url, data.get("totalCount", 0)):
            res.discovered.append(DiscoveredPage(
                url=u, category=Category.PROGRAM_CATALOG, title="Courses 枚举分页"))
        if not res.programs and "firstResult=0" in page.url:
            res.note("Courses 枚举首页未解析出专业")

    # ---------------- 课程：Coveo 枚举 JSON / SSR 详情页 ----------------
    def module_catalog(self, page, res):
        if COVEO_HOST in urlsplit(page.url).netloc:
            self._units_enum(page, res)
        else:
            self._unit_page(page, res)

    def _units_enum(self, page, res):
        try:
            data = json.loads(_text(page))
        except json.JSONDecodeError:
            res.note("units 枚举非 JSON")
            return
        for r in data.get("results", []):
            uri = r.get("clickUri") or (r.get("raw") or {}).get("uri")
            if uri and "/units/" in uri:
                res.discovered.append(DiscoveredPage(
                    url=uri, category=Category.MODULE_CATALOG,
                    title=norm_ws(r.get("title") or "")))
        for u in _next_coveo_urls(page.url, data.get("totalCount", 0)):
            res.discovered.append(DiscoveredPage(
                url=u, category=Category.MODULE_CATALOG, title="units 枚举分页"))

    def _unit_page(self, page, res):
        # h1 形如 "ECON1001: Introductory Microeconomics"
        h1 = page.h1() or ""
        m = re.match(r"\s*([A-Z]{2,4}\d{4})\s*:\s*(.+)", h1)
        if not m:
            res.note(f"unit 页 h1 非'代码:名称'格式: {h1[:40]}")
            return
        code, name = m.group(1), norm_ws(m.group(2))
        # /units/{code}/{2026-S1C-…} → 学期段
        seg = page.url.rstrip("/").split("/")[-1]
        sess = seg if re.match(r"20\d\d-", seg) else None
        credits = page.re(r"Credit points\s*</[^>]+>\s*<[^>]+>\s*(\d+)") \
            or page.re(r"(\d+)\s*credit point", flags=re.I)
        dept = page.re(r"(School of [A-Z][A-Za-z ,&]{3,45})\s+Student Portal")
        res.modules.append(ModuleData(
            name_en=name, url=page.url, entry_year=self.entry_year,
            code=code, dept=dept,
            credits=int(credits) if credits and str(credits).isdigit() else None,
            semester=sess))
