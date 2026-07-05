"""西澳大学（UWA）解析器 —— 澳洲第六所（2026-07-05 调研）。

数据拓扑（自建 handbook，老式聚合页——格拉待遇）：
- **课程名单一张索引页全拿**：handbooks.uwa.edu.au/units 列全 3,311 门
  （锚文本=课名，[代码] 在旁），unitdetails?code=X 是详情链接——
  详情页无归属字段（只有学分/学期/负责人），按克制原则不抓、存链接。
- 专业：/undergraduate + /postgraduate 列 coursedetails?code=N（PG 376 个），
  /majors 列 majordetails?code=MJD-XXX；**详情页有归属**
  （Administered by → 学院），要抓（~450 张）。
- 校历 = uwa.edu.au/students/my-course/important-dates：
  「日期行（23 February）+ 标签行（First day of semester (Semester 1, 2026)）」
  成对，年份在标签括号里。
- 反爬：无（纯 200）。
"""
import re

from parsers.base import BaseParser
from parsers.models import (CalendarData, DiscoveredPage, ModuleData,
                            ModuleRef, ProgramData)
from parsers.page import norm_ws
from parsers.uk.common import date_loose, event_type
from config.codes import Category, UniCode

UNIT_CODE_RE = re.compile(r"\[([A-Z]{3,6}\d{4})\]")


class UWA(BaseParser):
    uni_code = UniCode.UWA

    # ---------------- 目录 ----------------
    def program_catalog(self, page, res):
        if "/units" in page.url:          # 课程总索引：一页收全
            for a in page.soup.find_all("a", href=True):
                if "unitdetails?code=" not in a["href"]:
                    continue
                name = norm_ws(a.get_text(" ", strip=True))
                row = a.find_parent(["li", "tr"])
                m = UNIT_CODE_RE.search(row.get_text(" ", strip=True) if row else "")
                cm = re.search(r"code=([A-Z0-9]+)", a["href"])
                code = m.group(1) if m else (cm.group(1) if cm else None)
                if name and code:
                    lvl = re.search(r"[A-Z]+(\d)", code)
                    res.modules.append(ModuleData(
                        name_en=name, url=page.abs(a["href"]),
                        entry_year=self.entry_year, code=code,
                        level=f"L{lvl.group(1)}" if lvl else None))
            if not res.modules:
                res.note("units 索引页无课程行（站点结构变了？）")
            return
        # 学位/专业索引：coursedetails + majordetails 链接 → 详情任务
        seen = set()
        for a in page.soup.find_all("a", href=True):
            h = a["href"]
            if not re.search(r"(course|major)details\?code=", h):
                continue
            url = page.abs(h)
            if url in seen:
                continue
            seen.add(url)
            res.discovered.append(DiscoveredPage(
                url=url, category=Category.PROGRAM_DETAIL,
                title=norm_ws(a.get_text(" ", strip=True)) or None))
        if not res.discovered:
            res.note("学位索引页未解析出 course/major 链接")

    # ---------------- 专业详情（degree/major）----------------
    def program_detail(self, page, res):
        meta = _pairs(page)
        name = meta.get("Course title") or meta.get("Title") or _h1(page)
        if not name:
            res.note("详情页缺标题")
            return
        ctype = (meta.get("Course type") or "").lower()
        is_major = "majordetails" in page.url
        level = ("UG" if is_major or "bachelor" in ctype or "undergraduate" in ctype
                 else "PGT")
        p = ProgramData(
            name_en=(f"{name}（Major）" if is_major else name),
            level=level, url=page.url, entry_year=self.entry_year)
        p.faculty = meta.get("Administered by")
        # 课表引用：major/degree 页列出的 unitdetails 链接（按码挂到课程行）
        # ——units 全站无归属，课程在前端的显形通道就是这些专业课表（2026-07-05）
        seen = set()
        for a in page.soup.find_all("a", href=True):
            m2 = re.search(r"unitdetails\?code=([A-Z0-9]+)", a["href"])
            if not m2 or m2.group(1) in seen:
                continue
            seen.add(m2.group(1))
            p.modules.append(ModuleRef(
                name=norm_ws(a.get_text(" ", strip=True)) or m2.group(1),
                code=m2.group(1), url=page.abs(a["href"])))
        res.programs.append(p)

    # ---------------- 校历 ----------------
    def term_dates(self, page, res):
        """important-dates（实测 2026-07-05）：日期行在前、事件标签行在后，
        年份写在标签括号里（'(Semester 1, 2026)'）。"""
        pend = None            # 待配对的日期字符串
        for raw in [x.strip() for x in page.txt.split("\n") if x.strip()]:
            if re.fullmatch(r"\d{1,2} \w{3,9}( – \d{1,2} \w{3,9})?", raw):
                pend = raw
                continue
            if not pend or len(raw) > 120:
                continue
            ym = re.search(r"\b(20\d{2})\b", raw)
            year = ym.group(1) if ym else self.entry_year
            parts = re.split(r"\s*–\s*", pend)
            start = date_loose(f"{parts[0]} {year}")
            end = date_loose(f"{parts[-1]} {year}") if len(parts) > 1 else start
            label = norm_ws(raw)
            if start:
                res.calendar.append(CalendarData(
                    year, event_type(label, start), label, start, end or start))
            pend = None
        if not res.calendar:
            res.note("UWA important-dates 未解析出日期")


def _h1(page):
    h = page.soup.find("h1")
    return norm_ws(h.get_text(" ", strip=True)) if h else None


def _pairs(page):
    out = {}
    for dt in page.soup.find_all(["dt", "th"]):
        dd = dt.find_next_sibling(["dd", "td"])
        k = norm_ws(dt.get_text(" ", strip=True)).rstrip(":")
        if dd and k and k not in out:
            out[k] = norm_ws(dd.get_text(" ", strip=True))
    return out
