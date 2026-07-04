"""University of Sheffield parser."""
import re

from parsers.base import BaseParser
from parsers.models import CalendarData, DeadlineData, DiscoveredPage, ModuleRef, ProgramData
from parsers.page import norm_ws
from config.codes import EventType
from parsers.uk.common import (modules_from_credit_lis,
                               date_loose, date_range, find_links,
                               ielts, keyword_check, section_text, title_from)
from config.codes import Category, UniCode

COURSE_RE = r"/(?:undergraduate/courses|postgraduate/taught/courses)/20\d{2}/[^/?#]+/?$"
FACULTY_RE = r"Faculty of (?:Arts and Humanities|Engineering|Health|Science|Social Sciences)|International Faculty, CITY College"

# 集中截止日期页的措辞词典（实测 2026-07）：官网表格描述列 → (类型, 受众判断)
# 措辞是解析器的"翻译词典"数据，集中放表顶，逻辑不再直接内嵌字符串
DEADLINE_KEYWORDS = (
    # (描述列须含的措辞元组,   deadline_type, 受众规则: fixed 或 'visa_check')
    (("deposit deadline",),                        "deposit",     "international"),
    (("applications close", "last date to apply"), "application", "visa_check"),
)


class Sheffield(BaseParser):
    uni_code = UniCode.SHEF

    def program_catalog(self, page, res):
        for url, title, _ in find_links(page, COURSE_RE):
            res.discovered.append(DiscoveredPage(
                url=url, category=Category.PROGRAM_DETAIL, title=title or None))
        if not res.discovered:
            res.note("Sheffield 目录页未解析出课程详情链接")

    def program_detail(self, page, res):
        name = title_from(page, suffix_re=r"\s*\|\s*The University of Sheffield.*$")
        if not name:
            res.note("未解析出课程名称")
            return
        p = ProgramData(name_en=name, level="UG" if "/undergraduate/" in page.url else "PGT",
                        url=page.url, entry_year=_entry_year(page.url, self.entry_year))
        p.duration = _duration(page)
        p.dept = _dept(page)
        p.entry_req_text = section_text(page, r"Entry requirements", limit=800)
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        self._modules(page, p)
        if _fee_lookup(page):
            p.notes.append("学费由 courseFees JS lookup 提供，静态页金额置 None")
        res.programs.append(p)

    def _modules(self, page, p):
        """结构块 [class*=course-structure-module]，块内 '- 课程名 (15 credits)' 连写（实测 2026-07）。"""
        seen = set()
        for block in page.soup.select("[class*='course-structure-module']"):
            btxt = norm_ws(block.get_text(" ", strip=True))
            mtype = "optional" if re.search(r"optional", btxt[:120], re.I) else "core"
            for name, _cr in re.findall(r"([A-Z][^()\u2013-]{2,80}?)\s*\((\d{1,3})\s*credits?\)", btxt):
                n = norm_ws(name).strip("-\u2013 ")
                if n and n.lower() not in seen:
                    seen.add(n.lower())
                    p.modules.append(ModuleRef(name=n, module_type=mtype))
        modules_from_credit_lis(page, p, ModuleRef)   # PGT 页是 li 直列版式

    def term_dates(self, page, res):
        """dates 枢纽页 → 子页任务；学期页 = 每学年 Autumn/Spring 两张表
        （列: [Welcome week,] Start, End, Vacation, Weeks；实测 2026-07）。
        注：谢菲公开页不单列考试期（12 张表全为学期表），此为源站粒度上限。"""
        if re.search(r"/about/dates/?$", page.url):
            for url, title, _ in find_links(page, r"/about/dates/(?:current-and-future-semester|past|non-standard-semesters)"):
                res.discovered.append(DiscoveredPage(
                    url=url, category=Category.TERM_DATES, title=title or None))
            if not res.discovered:
                res.note("dates hub 未解析到子页面")
            return
        for tb in page.soup.find_all("table"):
            head = tb.find_previous(["h2", "h3"])
            season = norm_ws(head.get_text(" ", strip=True)) if head else "Semester"
            rows = []
            for tr in tb.find_all("tr"):
                cells = [norm_ws(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                if not cells:
                    continue
                has_welcome = len(cells) >= 5
                start = date_loose(cells[1] if has_welcome else cells[0])
                end = date_loose(cells[2] if has_welcome else cells[1])
                if not start:
                    continue
                ay = _academic_year(start)
                if has_welcome and cells[0]:
                    w0, w1 = date_range(cells[0])
                    if w0:
                        res.calendar.append(CalendarData(
                            ay, EventType.WELCOME_WEEK, "Welcome week", w0, w1))
                vac = cells[3] if has_welcome else (cells[2] if len(cells) > 2 else "")
                rows.append((ay, start, end, vac))
            for i, (ay, start, end, vac) in enumerate(rows):
                res.calendar.append(CalendarData(
                    ay, EventType.TEACHING_PERIOD, f"{season} 教学段{i+1}", start, end))
                # 假期区间 = 本段结束到下一段开始（源站只给假期名不给日期）
                if vac and i + 1 < len(rows):
                    res.calendar.append(CalendarData(
                        ay, EventType.CLOSURE, vac, end, rows[i+1][1]))
        if not res.calendar:
            res.note("Sheffield term dates 未解析出日期")


    def deadlines(self, page, res):
        for tr in page.soup.find_all("tr"):
            cells = [norm_ws(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
            if len(cells) < 2:
                continue
            d = date_loose(cells[0])
            if not d:
                continue
            low = cells[1].lower()
            for phrases, dtype, aud_rule in DEADLINE_KEYWORDS:
                if any(ph in low for ph in phrases):
                    aud = (("international" if "visa" in low else "all")
                           if aud_rule == "visa_check" else aud_rule)
                    res.deadlines.append(DeadlineData(
                        aud, dtype, d + " 23:59:00", self.entry_year, cells[1]))
                    break
        if not res.deadlines:
            res.note("Sheffield deadlines 未解析出截止日期")

    def fees(self, page, res):
        res.info("Sheffield fees lookup 作为参考页抓取")

    def language_req(self, page, res):
        overall, minimum = ielts(page.txt)
        if overall is None:
            res.note("未解析出 IELTS 数字")
        elif minimum is None:
            res.info(f"IELTS overall {overall}")
        else:
            res.info(f"IELTS overall {overall}, minimum {minimum}")

    def china_page(self, page, res):
        keyword_check(res, page, r"China", "Sheffield 中国专页")

    def faculty_list(self, page, res):
        if not re.search(FACULTY_RE, page.txt):
            res.note("未匹配到 Sheffield Faculty 名称")

    def ug_admissions(self, page, res):
        res.info("Sheffield UG 招生页作为参考页抓取")

    def pg_admissions(self, page, res):
        res.info("Sheffield PGT 招生页作为参考页抓取")


def _entry_year(url, default):
    m = re.search(r"/(20\d{2})/", url)
    return m.group(1) if m else default


def _duration(page):
    node = page.soup.select_one(".pgduration, #duration-list li, .duration-list-item")
    return norm_ws(node.get_text(" ", strip=True)) if node else None


def _dept(page):
    m = re.search(r"\b(School of [A-Z][A-Za-z &,\-]{3,80}|Management School|Information School)\b", page.txt)
    return norm_ws(m.group(1)) if m else None


def _fee_lookup(page):
    html = page.html.decode("utf-8", "ignore") if isinstance(page.html, bytes) else page.html
    return re.search(r'"courseFees"\s*:', html) is not None


def _row_dates(tr):
    headers = [norm_ws(th.get_text(" ", strip=True)) for th in tr.find_parent("table").find_all("th")]
    cells = [norm_ws(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
    try:
        return date_loose(cells[headers.index("Start date")]), date_loose(cells[headers.index("End date")])
    except (ValueError, IndexError, AttributeError):
        return None, None


def _academic_year(start_date):
    """9-12 月开始 → 当年启学年；1-8 月 → 上一年启学年。"""
    y, mth = int(start_date[:4]), int(start_date[5:7])
    sy = y if mth >= 9 else y - 1
    return f"{sy}/{str(sy + 1)[2:]}"
