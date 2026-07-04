"""University of Edinburgh parser."""
import re

from parsers.base import BaseParser
from parsers.models import (CalendarData, DeadlineData, DiscoveredPage,
                            ModuleData, ProgramData)
from parsers.page import norm_ws, parse_date
from parsers.uk.common import (date_range, event_type, ielts, keyword_check,
                               section_text)
from config.codes import Category, UniCode

PROGRAM_RE = r"/programmes/(?:undergraduate/(?:\d{4}/)?\d+|postgraduate-taught/\d+)-[^/?#]+/?$"


class Edinburgh(BaseParser):
    uni_code = UniCode.EDI

    def program_catalog(self, page, res):
        for row in page.soup.select(".views-row"):
            a = row.select_one(".views-field-title a[href]")
            if a and re.search(PROGRAM_RE, page.abs(a["href"]), re.I):
                res.discovered.append(DiscoveredPage(
                    url=page.abs(a["href"]), category=Category.PROGRAM_DETAIL,
                    title=norm_ws(a.get_text(" ", strip=True))))
        if not res.discovered:
            res.note("Degree Finder A-Z 未解析出专业链接")

    def program_detail(self, page, res):
        if page.url.rstrip("/").endswith("/entry-requirements"):
            return self._entry_requirements(page, res)
        name = page.h1()
        if not name:
            res.note("页面无 h1，跳过")
            return
        is_pg = "/postgraduate-taught/" in page.url
        p = ProgramData(name_en=name, level="PGT" if is_pg else "UG",
                        url=page.url, entry_year=self.entry_year)
        p.entry_year = page.re(r"Year of entry:?\s*\n?\s*(\d{4})") or p.entry_year
        p.ucas_code = _fact(page, "UCAS Code")
        p.campus = _fact(page, "Study location")
        p.dept = _fact(page, "School")
        p.faculty = _fact(page, "College")
        p.duration = _fact(page, "Duration of study") or _pg_duration(page)
        p.entry_req_text = section_text(
            page, r"Qualifications",
            r"English language requirements|Fees, costs|How to apply|Programme structure",
            500)
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        self._deadlines(page, p, is_pg)
        if p.tuition_intl is None:
            p.notes.append("学费金额未在主详情页内联")
        res.programs.append(p)
        # 静态的入学要求源数据子页（雅思/学历要求都在这，主页面是 JS 下拉）
        res.discovered.append(DiscoveredPage(
            url=page.url.rstrip("/") + "/entry-requirements",
            category=Category.PROGRAM_DETAIL, title=f"{name} · 入学要求源数据"))

    def _entry_requirements(self, page, res):
        """/entry-requirements 源数据子页：回填雅思与学历要求（实测 2026-07）。

        h1 形如 'Biological Sciences (Genetics) BSc (Hons)entry requirements'；
        ProgramData.url 指回主页面，loader 按 URL 兜底匹配已有专业行。
        """
        h1 = page.h1()
        if not h1:
            res.note("入学要求子页无 h1，跳过")
            return
        name = norm_ws(re.sub(r"entry requirements$", "", h1, flags=re.I))
        parent = page.url.rstrip("/").rsplit("/entry-requirements", 1)[0]
        p = ProgramData(name_en=name, url=parent, entry_year=self.entry_year,
                        level="PGT" if "/postgraduate-taught/" in page.url else "UG")
        m = re.search(r"IELTS Academic\s*\n?:?\s*total (\d(?:\.\d)?) with at least"
                      r" (\d(?:\.\d)?)", page.txt)
        if m:
            p.ielts_overall, p.ielts_min_each = float(m.group(1)), float(m.group(2))
        p.entry_req_text = (
            section_text(page, r"A [Ll]evels?", r"International Baccalaureate|GCSE", 300)
            or section_text(page, r"SQA Highers", r"A [Ll]evels?|International", 300))
        if not (p.ielts_overall or p.entry_req_text):
            res.note("入学要求子页未解析出雅思或学历要求")
            return
        res.programs.append(p)

    def _deadlines(self, page, p, is_pg):
        if not is_pg:
            d = page.date(r"UCAS deadline:\s*(\d{1,2} \w+ \d{4})", flags=re.I)
            if d:
                p.deadlines.append(DeadlineData(
                    "all", "equal_consideration", d + " 18:00:00", p.entry_year, "UCAS 常规截止"))
            return
        for table in page.soup.find_all("table"):
            headers = [norm_ws(th.get_text(" ", strip=True)).lower() for th in table.find_all("th")]
            if "application deadline" not in headers:
                continue
            idx = headers.index("application deadline")
            rnd = 0
            for tr in table.find_all("tr"):
                cells = [norm_ws(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                if len(cells) > idx:
                    d = parse_date(cells[idx])
                    if d:
                        rnd += 1
                        p.deadlines.append(DeadlineData(
                            "all", "round", d + " 23:59:00", p.entry_year,
                            f"第 {rnd} 轮申请截止", round_no=rnd))

    # ---------------- 官方课程目录（名单+链接，不镜像详情）----------------
    def module_catalog(self, page, res):
        """DRPS drps.ed.ac.uk（实测 2026-07）：cx_schindex 学院索引 →
        cx_s_su<id> 学院页（列科目）→ cx_sb_<subj> 科目页（课程名单）。
        课程链接文件名即课程代码（cxinfr08031.htm → INFR08031）；
        class=not_delivered 表示本学年不开课，跳过。策略同格拉：只收名单。"""
        if "cx_schindex" in page.url:
            for href, text in page.links(href_re=r"/cx_s_su\d+\.htm$"):
                name = norm_ws(re.sub(r"\(Schedule\s*[A-Z]?\s*\)\s*$", "", text))
                res.discovered.append(DiscoveredPage(
                    url=href, category=Category.MODULE_CATALOG,
                    title=f"{name} 科目索引"))
            if not res.discovered:
                res.note("DRPS 学院索引未解析出学院链接")
            return
        if re.search(r"/cx_s_su\d+\.htm$", page.url):
            for href, text in page.links(href_re=r"/cx_sb_\w+\.htm$"):
                res.discovered.append(DiscoveredPage(
                    url=href, category=Category.MODULE_CATALOG,
                    title=f"{text} 课程名单"))
            if not res.discovered:
                res.note("DRPS 学院页未解析出科目链接")
            return
        if "/cx_sb_" in page.url:
            school_links = page.links(href_re=r"/cx_s_su\d+\.htm$")
            dept = school_links[0][1] if school_links else None
            for a in page.soup.find_all("a", href=True):
                url = page.abs(a["href"])
                m = re.search(r"/cx([a-z]{2,6}\d{5})\.htm$", url)
                if not m or "not_delivered" in (a.get("class") or []):
                    continue
                name = norm_ws(a.get_text(" ", strip=True))
                if name:
                    res.modules.append(ModuleData(
                        name_en=name, url=url, entry_year=self.entry_year,
                        code=m.group(1).upper(), dept=dept))
            if not res.modules:
                res.note("DRPS 科目页无本学年开课的课程链接")

    def term_dates(self, page, res):
        # 未来学年子页（'/202627' 形）：登记为任务（实测 2026-07）
        for href, text in page.links(href_re=r"/20\d{4}/?$"):
            res.discovered.append(DiscoveredPage(
                url=href, category=Category.TERM_DATES, title=text or None))
        ym = page.re(r"Academic year\s+(\d{4}/\d{2})")
        if not ym:
            m = re.search(r"/(\d{4})(\d{2})/?$", page.url)
            ym = f"{m.group(1)}/{m.group(2)}" if m else None
        for tr in page.soup.select("table tr"):
            cells = [norm_ws(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
            if len(cells) != 2 or not ym:
                continue
            start, end = date_range(cells[0])
            if start:
                res.calendar.append(CalendarData(
                    ym, event_type(cells[1], start), cells[1], start, end))
        if not res.calendar:
            res.note("semester-dates 未解析出校历事件")

    def ug_admissions(self, page, res):
        d = page.date(r"(\d{1,2} January 20\d{2})\s*\nUCAS Equal consideration", flags=re.I)
        if d:
            res.deadlines.append(DeadlineData(
                "all", "equal_consideration", d + " 18:00:00",
                self.entry_year, "UCAS equal consideration date"))
        else:
            res.note("Edinburgh UG admissions 未解析出 equal consideration 日期")

    def pg_admissions(self, page, res):
        res.info("Edinburgh PGT 截止日期按 degree finder 专业页解析")

    def faculty_list(self, page, res):
        txt = page.txt.replace("&", "and")
        if not any(name.replace("&", "and") in txt for name in self.conf.faculties):
            res.note("未匹配到 Edinburgh College 名称")

    def china_page(self, page, res):
        keyword_check(res, page, r"China", "Edinburgh 中国专页")


def _fact(page, label):
    for b in page.soup.find_all("b"):
        if norm_ws(b.get_text(" ", strip=True)).rstrip(":").lower() != label.lower():
            continue
        text = norm_ws(b.find_parent().get_text(" ", strip=True))
        return re.sub(r"^" + re.escape(label) + r":?\s*", "", text, flags=re.I) or None
    return None


def _pg_duration(page):
    m = re.search(r"\b(?:MSc|MA|LLM|MScR)\s*\|\s*([^|\n]+)\s*\|", page.txt)
    return norm_ws(m.group(1)) if m else None
