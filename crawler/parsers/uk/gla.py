"""格拉斯哥大学解析器（选择器实测于 2026-07）。

页面特点（对比 UCL）：
- 目录页 ul.programme-list：纯 <li><a>Name[MSc/PgDip]</a></li>，卡上无院系 →
  院系在专业页正文规范化（canon_faculty + gla.yaml 官方 School 清单）；
- 专业页 h1 是栏目名，真实项目名在 <title> 尾段；
- 雅思直接给分（非 UCL 分级制）；PGT 页费用/截止文本模式固定；
- UG 专业页不标学费数额，申请季标在 'for entry in YYYY'。
"""
import re
from datetime import datetime

from parsers.base import BaseParser
from parsers.models import ModuleRef
from parsers.uk.common import event_type, modules_from_credit_lis
from parsers.models import CalendarData, DeadlineData, DiscoveredPage, ProgramData
from parsers.page import parse_date
from config.codes import Category, UniCode

SCHOOL_RE = r"(Adam Smith Business School|School of [A-Z][A-Za-z ,&\-]{3,70})"


class Glasgow(BaseParser):
    uni_code = UniCode.GLA

    # ---------------- 目录页 ----------------
    def program_catalog(self, page, res):
        is_pg = "/postgraduate/" in page.url
        href_re = (r"/postgraduate/taught/[a-z0-9-]+/?$" if is_pg
                   else r"/undergraduate/degrees/[a-z0-9-]+/?$")
        for href, raw in page.links("ul.programme-list", href_re):
            # 卡片文本 'Data Analytics[MSc: Online]' → 名称 + 学位
            m = re.match(r"^(.*?)\[(.*?)\]$", raw)
            name, degrees = (m.group(1).strip(), m.group(2).strip()) if m else (raw, "")
            res.discovered.append(DiscoveredPage(
                url=href, category=Category.PROGRAM_DETAIL,
                title=f"{name} [{degrees}]" if degrees else name))
        if not res.discovered:
            res.note("目录页未解析出 programme-list 项目链接，页面结构可能已变")

    # ---------------- 专业页 ----------------
    def program_detail(self, page, res):
        name = page.title_tail()
        if not name or len(name) < 3:
            res.note("未从 <title> 解析出项目名，可能非专业页")
            return
        is_pg = "/postgraduate/" in page.url
        p = ProgramData(name_en=name, level="PGT" if is_pg else "UG",
                        url=page.url, entry_year=self.entry_year)

        # 申请季 + 学费（PGT 页固定文本；UG 页无数额，留 None）
        label = page.re(r"Tuition fees for (\d{4}-\d{2})")
        if label:
            p.fee_year_label = label
            p.entry_year = label.split("-")[0]
        p.tuition_home = page.money(r"Home & RUK\s*\n(?:Full-time fee:\s*\n)?£([\d,]+)")
        p.tuition_intl = page.money(r"International & EU\s*\n(?:Full-time fee:\s*\n)?£([\d,]+)")

        # 学制：'MSc: \n 12 months full-time'；UG 从 '(4 years)'
        p.duration = page.re(r"\n(?:MSc|MRes|MEd|LLM|MBA|MLitt|MMus)[^\n]*:\s*\n"
                             r"(\d+ months? [a-z -]+)")
        if not p.duration and not is_pg:
            yrs = page.re(r"\((\d) years?\)")
            p.duration = f"{yrs} years" if yrs else None

        # 申请季（UG 页标在要求区块）/ 学术要求 / 雅思
        if not is_pg:
            y = page.re(r"Entry requirements\s*\nfor entry in (\d{4})")
            if y:
                p.entry_year = y
        p.entry_req_text = page.re(
            r"Entry requirements\s*\n(?:for entry in \d{4}\s*\n)?([^\n]{10,300})")
        m = re.search(r"IELTS[^\n]*\n?[^\n]*?(\d\.\d|\d) (?:overall )?with no subtests?"
                      r"(?: less than| under) (\d\.\d|\d)", page.txt)
        if m:
            p.ielts_overall, p.ielts_min_each = float(m.group(1)), float(m.group(2))

        # 院系：正文 School 提及规范化到官方清单
        p.dept = self.canon_faculty(page.txt, SCHOOL_RE)

        self._deadlines(page, p, is_pg)
        self._modules(page, p)
        if p.tuition_intl is None and is_pg:
            p.notes.append("未解析出国际学费，页面结构可能已变，需人工核对")
        res.programs.append(p)

    @staticmethod
    def _modules(page, p):
        modules_from_credit_lis(page, p, ModuleRef, scope_css="div.tab-content li")

    def _deadlines(self, page, p, is_pg):
        if is_pg:
            d = page.date(r"International & EU applicants\s*\n(\d{1,2} \w+ \d{4})")
            if d:
                p.deadlines.append(DeadlineData(
                    "international", "application", d + " 23:59:00",
                    p.entry_year, "国际/欧盟申请者截止"))
            d = page.date(r"Home applicants\s*\n(\d{1,2} \w+ \d{4})")
            if d:
                p.deadlines.append(DeadlineData(
                    "home", "application", d + " 23:59:00",
                    p.entry_year, "本土申请者截止"))
            return
        # UG 走 UCAS，截止日期不带年份，年份 = 申请季年（入学当年 1 月）
        m = page.re(r"(\d{1,2} January)\s*\n?:?\s*\n?all other", flags=re.I)
        if m:
            d = parse_date(f"{m} {p.entry_year}")
            if d:
                p.deadlines.append(DeadlineData(
                    "all", "equal_consideration", d + " 18:00:00",
                    p.entry_year, "UCAS 常规截止"))
        m = page.re(r"(\d{1,2} \w+)\s*\n?:?\s*\n?international students", flags=re.I)
        if m:
            d = parse_date(f"{m} {p.entry_year}")
            if d:
                p.deadlines.append(DeadlineData(
                    "international", "application", d + " 23:59:00",
                    p.entry_year, "国际学生截止"))
        p.ucas_code = page.re(r"Apply to ([A-Z]{1,2}\d{2}[A-Z0-9]?)\b")

    # ---------------- 校历 ----------------
    def term_dates(self, page, res):
        """sessiondates 根页 → 各学年子页任务；学年子页表格 → 校历事件。"""
        m = re.search(r"session(\d{4})-(\d{2})/?$", page.url)
        if not m:   # 根页：发现各学年子页
            for href, text in page.links(href_re=r"/sessiondates/session\d{4}-\d{2}/?$"):
                res.discovered.append(DiscoveredPage(
                    url=href, category=Category.TERM_DATES, title=text))
            if not res.discovered:
                res.note("sessiondates 根页未发现学年子页链接")
            return

        year_label = f"{m.group(1)}/{m.group(2)}"
        table = page.soup.find("table")
        if not table:
            res.note("学年页无日期表格")
            return
        points, ranges = self._table_points(table)
        events = self._pair_events(points) + ranges
        events = self._disambiguate(events)
        for name, start, end in events:
            res.calendar.append(CalendarData(
                academic_year=year_label, event_type=event_type(name, start),
                name=name, start_date=start, end_date=end))
        if not res.calendar:
            res.note("学年页表格未解析出任何事件")

    @staticmethod
    def _table_points(table):
        """两种历史格式：A=6列点事件（年/月向下继承）；B=2列（完整日期或日期区间）。"""
        points: list = []
        ranges: list = []
        year = month = None

        def iso(day, mon, yr):
            return parse_date(f"{day} {mon} {yr}")

        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) >= 5:          # 格式 A
                year = cells[0] or year
                month = cells[1] or month
                if cells[3].isdigit() and year and month:
                    date = iso(cells[3], month, year)
                    if date:
                        points.extend((date, t) for t in cells[4:6] if t)
            elif len(cells) == 2:        # 格式 B
                dtxt, ev = cells
                mr = re.match(r"\w+ (\d{1,2})(?: (\w+))?(?: (\d{4}))? ?- ?"
                              r"\w+ (\d{1,2}) (\w+) (\d{4})$", dtxt)
                if mr:
                    d1 = iso(mr.group(1), mr.group(2) or mr.group(5),
                             mr.group(3) or mr.group(6))
                    d2 = iso(mr.group(4), mr.group(5), mr.group(6))
                    if d1 and d2:
                        ranges.append((ev, d1, d2))
                    continue
                ms = re.match(r"\w+ (\d{1,2}) (\w+) (\d{4})$", dtxt)
                if ms:
                    date = iso(ms.group(1), ms.group(2), ms.group(3))
                    if date:
                        points.append((date, ev))
        return points, ranges

    @staticmethod
    def _pair_events(points):
        """'Start of X'/'End of X'（或 'X starts/ends'）时间点配对成区间。"""
        events, opens = [], []
        for date, text in points:
            ms = re.match(r"Start of (.+)$", text) or re.match(r"(.+?) starts$", text)
            if ms:
                opens.append([ms.group(1).strip(), date])
                continue
            me = re.match(r"End of (.+?)(?: / .*)?$", text) or re.match(r"(.+?) ends$", text)
            if me:
                key = me.group(1).strip().lower()
                hit = next((o for o in opens
                            if o[0].lower().startswith(key) or key.startswith(o[0].lower())),
                           None)
                if hit:
                    opens.remove(hit)
                    events.append((hit[0], hit[1], date))
                else:
                    events.append((text, date, None))
                continue
            events.append((text, date, None))
        events.extend(("Start of " + name, start, None) for name, start in opens)
        return events

    @staticmethod
    def _disambiguate(events):
        """同学年同名事件（如两个毕业典礼期）加月份后缀，避免唯一键互相覆盖。"""
        seen, out = set(), []
        for name, start, end in sorted(events, key=lambda e: e[1]):
            if name in seen:
                name = f"{name} ({datetime.strptime(start, '%Y-%m-%d').strftime('%b')})"
            seen.add(name)
            out.append((name, start, end))
        return out

