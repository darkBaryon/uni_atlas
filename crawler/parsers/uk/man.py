"""University of Manchester parser."""
import re

from parsers.base import BaseParser
from parsers.models import (CalendarData, DeadlineData, DiscoveredPage,
                            ModuleData, ModuleRef, ProgramData)
from parsers.page import norm_ws, parse_date
from parsers.uk.common import date_loose, event_type, fee_near, find_links, first, ielts, section_text
from config.codes import Category, FetchMethod, UniCode

COURSE_RE = r"/study/(?:undergraduate/courses/2026|masters/courses/list)/\d{4,6}/[^/?#]+/?$"
MODULE_CODE_RE = re.compile(r"\b[A-Z]{4}\d{4,5}\b")


class Manchester(BaseParser):
    uni_code = UniCode.MAN

    def program_catalog(self, page, res):
        for url, title, _ in find_links(page, COURSE_RE):
            res.discovered.append(DiscoveredPage(
                url=url, category=Category.PROGRAM_DETAIL, title=title or None))
        if not res.discovered:
            res.note("未解析出 Manchester 专业链接")

    def program_detail(self, page, res):
        name = page.h1()
        if not name:
            res.note("页面无 h1，跳过")
            return
        is_pg = "/study/masters/" in page.url
        p = ProgramData(name_en=name, level="PGT" if is_pg else "UG",
                        url=page.url, entry_year=self.entry_year)
        p.entry_year = first(page.txt, r"Year of entry:?\s*\n?\s*(\d{4})") or p.entry_year
        p.duration = first(page.txt, r"Duration:?\s*\n?\s*([^\n]+)")
        p.ucas_code = first(page.txt, r"UCAS course code:?\s*\n?\s*([A-Z0-9]{4,5})")
        p.tuition_home = fee_near(page.txt, ("home students", "UK students"))
        p.tuition_intl = fee_near(page.txt, ("international students", "International, including EU"))
        p.fee_year_label = first(page.txt, r"(\d{4}/\d{2}) academic year")
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        p.entry_req_text = section_text(
            page,
            r"Academic entry qualification overview|Typical A-level offer|A-level",
            r"English language|Fees and funding|Application and selection",
            500,
        )
        p.dept = _dd(page, "Department") or _dd(page, "School/Faculty")
        self._deadlines(page, p, is_pg)
        self._modules(page, p)
        if p.tuition_intl is None:
            p.notes.append("未解析出国际学费")
        res.programs.append(p)

    def _deadlines(self, page, p, is_pg):
        if not is_pg:
            d = page.date(r"UCAS[^\n]{0,120}?(\d{1,2} \w+ \d{4})", flags=re.I)
            d = d or ("2026-01-14" if p.entry_year == "2026" else None)
            if d:
                p.deadlines.append(DeadlineData(
                    "all", "equal_consideration", d + " 18:00:00",
                    p.entry_year, "UCAS 常规截止"))
            return
        for raw in re.findall(r"Application received by\s+(\d{1,2} \w+ \d{4})",
                              page.txt, re.I):
            d = parse_date(raw)
            if d:
                p.deadlines.append(DeadlineData(
                    "all", "round", d + " 23:59:00", p.entry_year, "分轮申请截止"))

    def _modules(self, page, p):
        for table in page.soup.find_all("table"):
            headers = [norm_ws(th.get_text(" ", strip=True)) for th in table.find_all("th")]
            if "Title" not in headers or "Code" not in headers:
                continue
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) < 2:
                    continue
                title = norm_ws(cells[0].get_text(" ", strip=True))
                code = norm_ws(cells[1].get_text(" ", strip=True))
                m = MODULE_CODE_RE.search(code) or MODULE_CODE_RE.search(title)
                if title:
                    p.modules.append(ModuleRef(
                        name=MODULE_CODE_RE.sub("", title).strip(),
                        code=m.group(0) if m else None,
                        module_type="core" if "mandatory" in norm_ws(cells[-1].get_text(" ", strip=True)).lower()
                        else "optional"))

    # ---------------- 官方课程目录（名单+链接，不镜像详情）----------------
    # MyManchester uPortal course-unit-info portlet，免登录（探明 2026-07-04）。
    # 表单页(render.uP)枚举 ~75 学科 → 每学科×career 一个 POST 检索任务
    # (portlet_post，参数全在 URL query) → 结果表: 代码/名称/level/学期/学分/
    # Valid From（同代码多行取最新）。坑: app.manchester.ac.uk 直访 .xml
    # 返回 200 的伪 404，必须经门户 portlet 代理。
    PORTLET = "https://portal.manchester.ac.uk/uPortal/p/course-unit-info.ctf1/max"
    CAREERS = ("UGRD", "PGDT")     # 辅导相关：本科 + 授课硕士
    SUBJECT_OPT_RE = r"/CourseUnitbyCareerSubjectArea/([A-Z0-9]+)\.xml"
    UNIT_CODE_RE = r"[A-Z]{2,6}\d{5}"

    def module_catalog(self, page, res):
        from urllib.parse import quote
        if "/render.uP" in page.url:          # 表单页：学科下拉 → 检索任务
            for opt in page.soup.select("option"):
                val = str(opt.get("value") or "")
                if not re.search(self.SUBJECT_OPT_RE, val):
                    continue
                label = norm_ws(opt.get_text(" ", strip=True))
                for career in self.CAREERS:
                    res.discovered.append(DiscoveredPage(
                        url=(f"{self.PORTLET}/action.uP?pP_action=searchCUCatalog"
                             f"&career={career}&searchCriteria=subject"
                             f"&subjectArea={quote(val, safe='')}"),
                        category=Category.MODULE_CATALOG,
                        fetch_method=FetchMethod.PORTLET_POST,
                        title=f"{label} 课程名单（{career}）"))
            if not res.discovered:
                res.note("portlet 表单页未枚举到学科（门户结构变了？）")
            return
        best: dict[str, tuple[str, ModuleData]] = {}   # 结果页：code -> (生效日, ModuleData)
        for table in page.soup.select("table"):
            head = [th.get_text(" ", strip=True).lower() for th in table.select("th")]
            if not head or "unit code" not in head[0]:
                continue
            for tr in table.select("tr"):
                tds = tr.select("td")
                if len(tds) < 7:
                    continue
                cells = [norm_ws(td.get_text(" ", strip=True)) for td in tds]
                code, name, level, sem, credits, _free, valid = cells[:7]
                if not re.fullmatch(self.UNIT_CODE_RE, code) or not name:
                    continue
                a = tds[1].select_one("a[href]")
                href = str(a["href"]) if a else ""
                if not href.startswith("/"):
                    continue
                m = ModuleData(
                    name_en=name, url="https://portal.manchester.ac.uk" + href,
                    entry_year=self.entry_year, code=code,
                    credits=int(credits) if credits.isdigit() else None,
                    level=f"Level {level}" if level else None,
                    semester=sem or None)
                valid_key = parse_date(valid) or ""    # '01 Aug 2025' 字符串不可比，转 ISO
                if code not in best or valid_key > best[code][0]:
                    best[code] = (valid_key, m)
        res.modules.extend(m for _v, m in best.values())
        if not res.modules:
            res.note("portlet 检索页无课程行（该学科×career 可能确实无课）")

    def term_dates(self, page, res):
        for h2 in page.soup.find_all("h2"):
            m = re.search(r"(\d{4})/(\d{2}) academic year", h2.get_text(" ", strip=True))
            if not m:
                continue
            table = h2.find_next("table")
            if not table:
                continue
            year = f"{m.group(1)}/{m.group(2)}"
            for tr in table.find_all("tr"):
                cells = [norm_ws(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                if len(cells) < 2:
                    continue
                start = date_loose(cells[1])
                end = date_loose(cells[2]) if len(cells) > 2 else None
                if start:
                    res.calendar.append(CalendarData(
                        year, event_type(cells[0], start), cells[0], start, end))
        if not res.calendar:
            res.note("Manchester key-dates 未解析出校历表格")

    def ug_admissions(self, page, res):
        d = page.date(r"(\d{1,2} January 20\d{2})\s*\nEqual consideration", flags=re.I)
        d = d or page.date(r"Equal consideration[^\n]{0,180}(\d{1,2} \w+ 20\d{2})", flags=re.I | re.S)
        d = d or ("2026-01-14" if self.entry_year == "2026" else None)
        if d:
            res.deadlines.append(DeadlineData(
                "all", "equal_consideration", d + " 18:00:00",
                self.entry_year, "UCAS 常规截止"))
        else:
            res.note("Manchester UG admissions 未解析出 equal consideration 日期")

    def pg_admissions(self, page, res):
        res.info("Manchester PGT 截止日期在专业页解析")

    def faculty_list(self, page, res):
        if not any(name in page.txt for name in self.conf.faculties):
            res.note("未匹配到 Manchester Faculty 名称")

    def china_page(self, page, res):
        if "China" not in page.txt:
            res.note("China 页面未匹配到 China 关键词")


def _dd(page, label):
    for dt in page.soup.find_all("dt"):
        if norm_ws(dt.get_text(" ", strip=True)).lower() == label.lower():
            dd = dt.find_next_sibling("dd")
            return norm_ws(dd.get_text(" ", strip=True)) if dd else None
    return None
