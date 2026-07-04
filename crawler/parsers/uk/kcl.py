"""KCL 伦敦国王学院解析器（选择器实测 2026-07）。

注意：目录页 JS 懒加载（静态 HTML 只出首屏 15 条，source_pages 已标
js_render 待 Playwright）；语言要求为 Band A-E 分级制。
"""
from parsers.base import BaseParser
from parsers.page import norm_ws
from parsers.models import (CalendarData, DeadlineData, DiscoveredPage,
                            ModuleData, ProgramData)
from parsers.uk.common import (band, date_range, event_type, fee_near,
                               find_links, first, ielts,
                               keyword_check, known_name,
                               section_text, standard_deadlines, title_from)
import re

from config.codes import Category, UniCode

COURSE_RE = (r"/study/(?:undergraduate|postgraduate-taught)/courses/"
             r"(?!course-types-and-study-options/?$)[a-z0-9-]+/?$")


class KCL(BaseParser):
    uni_code = UniCode.KCL

    def program_catalog(self, page, res):
        # A-Z 列表是 React SPA（静态只出首屏），全量清单在编号 sitemap
        # sitemap1-8.xml 的 <loc> 里（主 sitemap.xml 不含，实测 2026-07）
        if "sitemap" in page.url:
            for loc in page.soup.select("loc"):
                url = norm_ws(loc.get_text(strip=True))
                if re.search(COURSE_RE, url):
                    res.discovered.append(DiscoveredPage(
                        url=url, category=Category.PROGRAM_DETAIL))
            if not res.discovered:
                res.info("该编号 sitemap 无课程 URL（部分 sitemap 属其他板块，预期内）")
            return
        for url, title, _ in find_links(page, COURSE_RE):
            res.discovered.append(DiscoveredPage(
                url=url, category=Category.PROGRAM_DETAIL, title=title or None))
        if not res.discovered:
            res.note("KCL 目录页未解析出静态课程链接（JS 懒加载，属预期）")

    def program_detail(self, page, res):
        name = title_from(
            page, bad_h1=("King's College London",),
            suffix_re=r"\s*\|\s*King's College London.*$")
        if not name:
            res.note("未解析出课程标题")
            return
        p = ProgramData(name_en=name, url=page.url, entry_year=self.entry_year,
                        level="UG" if "/undergraduate/" in page.url else "PGT")
        p.duration = first(page.txt, r"(?:Duration|Course length|Length)\s*\n([^\n]{2,120})")
        p.ucas_code = page.re(r"UCAS(?: course)? code\s*\n?\s*([A-Z0-9]{4,5})")
        p.campus = first(page.txt, r"(?:Campus|Location|Teaching location)\s*\n([^\n]{2,120})")
        p.tuition_home = fee_near(page.txt, ("Home fee", "UK fee", "Home:"))
        p.tuition_intl = fee_near(page.txt, ("International fee", "Overseas fee", "International:"))
        p.entry_req_text = section_text(
            page, r"Entry requirements|Academic requirements",
            r"English language requirements|Fees and funding|Teaching|Apply|Careers",
            500)
        p.faculty = known_name(self.conf.faculties, page.txt)
        p.language_band = band(page.txt, letters="A-E")
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        standard_deadlines(page, p, DeadlineData)
        if p.tuition_intl is None:
            p.notes.append("未解析出国际学费")
        res.programs.append(p)

    # ---------------- 模块目录（交换生子集——KCL 唯一公开模块源）----------------
    # /abroad/module-options（实测 2026-07）：browse 页 ~37 院系 →
    # search?dept=<code> 每模块一个 article（Module code/Level/Semester/
    # Credit value/Department），标题在 article 前的 heading（带 "Level N" 尾）。
    # 仅覆盖对交换生开放的模块（大子集，非全量）；主课程页只有散文无结构。
    def module_catalog(self, page, res):
        if "dept=" not in page.url:       # browse 根页 → 各院系检索页
            for href, text in page.links(href_re=r"/abroad/module-options/search\?dept="):
                res.discovered.append(DiscoveredPage(
                    url=href, category=Category.MODULE_CATALOG,
                    title=f"{text} 模块名单（交换生目录）",
                    note="交换生模块目录（公开子集，非全量）"))
            if not res.discovered:
                res.note("browse 页未解析出院系链接")
            return
        for art in page.soup.select("article"):
            txt = art.get_text("\n", strip=True)
            code = first(txt, r"Module code:\s*\n?([0-9][A-Z]{3}[0-9A-Z]{3,6})")
            if not code:
                continue
            head = art.find_previous(["h2", "h3", "h4"])
            name = norm_ws(re.sub(r"\s*Level \d+$", "",
                                  head.get_text(" ", strip=True))) if head else ""
            if not name:
                continue
            level = first(txt, r"Level:\s*\n?(\d)")
            credits = first(txt, r"Credit value:\s*\n?(\d{1,3})")
            dept = first(txt, r"Department:\s*\n?([^\n]+)")
            res.modules.append(ModuleData(
                name_en=name, url=page.url, entry_year=self.entry_year, code=code,
                credits=int(credits) if credits else None,
                level=f"Level {level}" if level else None,
                semester=first(txt, r"Semester:\s*\n?([^\n]+)"),
                dept=dept))
        if not res.modules:
            res.note("模块检索页无 article 行（该院系可能无开放模块）")

    def term_dates(self, page, res):
        """版式（实测 2026-07）：'2025-26 Academic Calendar' 学年标题 →
        'Semester N' 小节 → '标签: Weekday DD – Weekday DD Month YYYY' 行。"""
        year = sem = None
        for line in page.txt.splitlines():
            line = norm_ws(line)
            m = re.match(r"(20\d{2})-(\d{2}) Academic Calendar", line)
            if m:
                year, sem = f"{m.group(1)}/{m.group(2)}", None
                continue
            if re.fullmatch(r"Semester \d", line):
                sem = line
                continue
            if ":" not in line or not year:
                continue
            label, _, rest = line.partition(":")
            label = norm_ws(label)
            if label.lower() == "academic year":   # 学年整体区间，噪音
                continue
            start, end = date_range(rest)
            if not start:
                continue
            name = f"{sem} {label}" if sem else label
            res.calendar.append(CalendarData(
                year, event_type(name, start), name, start, end))
        if not res.calendar:
            res.note("KCL 校历页未解析出日期区间")


    def ug_admissions(self, page, res):
        keyword_check(res, page, r"deadline|UCAS", "KCL UG 招生页")

    def pg_admissions(self, page, res):
        keyword_check(res, page, r"deadline|UCAS", "KCL PGT 招生页")

    def language_req(self, page, res):
        keyword_check(res, page, r"\bBand\s+[A-E]\b", "KCL 语言分级页")

    def china_page(self, page, res):
        keyword_check(res, page, r"China|East Asia", "KCL 中国专页")

    def faculty_list(self, page, res):
        if not known_name(self.conf.faculties, page.txt):
            res.note("未匹配到 KCL Faculty 名称")
