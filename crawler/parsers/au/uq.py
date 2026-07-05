"""昆士兰大学 UQ 解析器（study.uq 营销层 + programs-courses CDP，实测 2026-07）。

数据分工（programs-courses 挂 AWS WAF 人工 CAPTCHA，只能经 cdp 会话）：
- program_catalog（study.uq sitemap，html）→ 发现专业页任务；
- program_detail（study.uq 专业页，html）→ ProgramData（名 json-ld / level 由名判）
  + 发现该专业的 CDP requirements 页（拿课程码 + 院系）；
- module_catalog 两形态（按 URL 分流，均 cdp）：
  * requirements/program → 抠 window.AppData 里的课程码 → 发现课程页任务；
  * course.html?course_code=XXX → 课程 SSR 页 → ModuleData（h1='课名 (码)'、level、院系）。
"""
import json
import re

from parsers.base import BaseParser
from parsers.models import DiscoveredPage, ModuleData, ProgramData
from parsers.page import norm_ws
from config.codes import Category, FetchMethod, UniCode

PC = "programs-courses.uq.edu.au"
CODE_RE = re.compile(r"\b([A-Z]{4}\d{4})\b")


def _text(page):
    h = page.html
    return h.decode("utf-8", "replace") if isinstance(h, bytes) else h


def _level(name):
    n = name.lower()
    if any(w in n for w in ("doctor", "phd", "(honours)", "mphil")):
        return "PGR" if ("doctor" in n or "phd" in n or "mphil" in n) else "UG"
    if any(w in n for w in ("master", "graduate certificate", "graduate diploma",
                            "postgraduate")):
        return "PGT"
    return "UG"


def _appdata(html):
    m = re.search(r"window\.AppData\s*=\s*(\{)", html)
    if not m:
        return None
    i = m.start(1)
    depth = 0
    for j in range(i, len(html)):
        if html[j] == "{":
            depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[i:j + 1])
                except json.JSONDecodeError:
                    return None
    return None


class UQ(BaseParser):
    uni_code = UniCode.UQ

    # ---------------- study.uq sitemap → 专业页 ----------------
    def program_catalog(self, page, res):
        html = _text(page)
        seen = set()
        for m in re.finditer(r"https://study\.uq\.edu\.au/study-options/programs/"
                             r"([a-z0-9-]+-\d{4})\b", html):
            slug = m.group(1)
            if slug in seen:
                continue
            seen.add(slug)
            res.discovered.append(DiscoveredPage(
                url=f"https://study.uq.edu.au/study-options/programs/{slug}",
                category=Category.PROGRAM_DETAIL))
        if not res.discovered:
            res.note("study.uq sitemap 未解析出专业链接")

    # ---------------- study.uq 专业页 → ProgramData + CDP requirements ----------------
    def program_detail(self, page, res):
        html = _text(page)
        m = re.search(r"study-options/programs/[a-z0-9-]+-(\d{4})", page.url)
        pid = m.group(1) if m else None
        # 名字优先 json-ld
        name = None
        for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                              html, re.S):
            try:
                d = json.loads(blk)
            except json.JSONDecodeError:
                continue
            nm = d.get("name") if isinstance(d, dict) else None
            if nm and nm not in ("Study", "The University of Queensland"):
                name = norm_ws(nm)
                break
        if not name:
            t = re.search(r"<title>([^<|]+)", html)
            name = norm_ws(t.group(1)) if t else None
        if not name:
            res.note(f"专业页未解析出名字: {page.url[-30:]}")
            return
        # 去站名后缀（json-ld/title 都可能带 " - Study - The University of Queensland"）
        name = re.sub(r"\s*[-|]\s*(Study\s*[-|]\s*)?The University of Queensland.*$",
                      "", name).strip()
        p = ProgramData(name_en=name, level=_level(name), url=page.url,
                        entry_year=self.entry_year, currency="AUD")
        res.programs.append(p)
        # 发现 CDP requirements 页（拿课程 + 院系）
        if pid:
            res.discovered.append(DiscoveredPage(
                url=f"https://{PC}/requirements/program/{pid}/{self.entry_year}",
                category=Category.MODULE_CATALOG, fetch_method=FetchMethod.CDP,
                title=name))

    # ---------------- CDP：requirements 枚举课程 / course 详情 ----------------
    def module_catalog(self, page, res):
        if "/requirements/program/" in page.url:
            self._program_reqs(page, res)
        elif "course.html" in page.url:
            self._course_page(page, res)

    def _program_reqs(self, page, res):
        html = _text(page)
        d = _appdata(html)
        pr = (d or {}).get("programRequirements") or {}
        s = json.dumps(pr, ensure_ascii=False)
        codes = sorted(set(CODE_RE.findall(s)))
        for code in codes:
            res.discovered.append(DiscoveredPage(
                url=f"https://{PC}/course.html?course_code={code}",
                category=Category.MODULE_CATALOG, fetch_method=FetchMethod.CDP,
                title=code))
        if not codes:
            res.note(f"requirements 页无课程码（可能是纯 plan 容器）: {page.url[-20:]}")

    def _course_page(self, page, res):
        html = _text(page)
        # h1 第二个通常是 "Introduction to Software Engineering (CSSE1001)"
        name = code = None
        for h1 in re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S):
            txt = norm_ws(re.sub(r"<[^>]+>", "", h1))
            m = re.match(r"(.+?)\s*\(([A-Z]{4}\d{4})\)\s*$", txt)
            if m:
                name, code = m.group(1), m.group(2)
                break
        if not name or not code:
            res.note(f"课程页未解析出 '课名 (码)': {page.url[-25:]}")
            return
        text = re.sub(r"<[^>]+>", "\n", html)
        lvl = re.search(r"Course level\s*\n\s*(Undergraduate|Postgraduate)", text)
        # 版式：Units 标签 → 解释文字 → 数值 → Duration；取紧挨 Duration 前的数字
        units = re.search(r"(\d{1,2})\s+Duration\b", text)
        dept = re.search(r"(?:Faculty|School)\s*\n\s*([A-Z][A-Za-z ,&]{4,45})", text)
        res.modules.append(ModuleData(
            name_en=name, url=page.url, entry_year=self.entry_year, code=code,
            level=("UG" if lvl and lvl.group(1) == "Undergraduate" else
                   ("PGT" if lvl else None)),
            credits=int(units.group(1)) if units else None,
            dept=norm_ws(dept.group(1)) if dept else None))
