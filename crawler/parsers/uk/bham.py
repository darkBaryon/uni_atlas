"""University of Birmingham parser."""
import re

from parsers.base import BaseParser
from parsers.models import ModuleData, CalendarData, DiscoveredPage, ModuleRef, ProgramData
from parsers.page import norm_ws
from parsers.uk.common import (date_range, event_type, fee_near, find_links,
                               ielts, keyword_check, section_text, title_from)
from config.codes import Category, UniCode

COURSE_RE = r"/study/(?:undergraduate|postgraduate)/subjects/.+-courses/[^/?#]+/?$"
# 校历页整句措辞 → 短名（实测 2026-07；页面不单列考试期，为源站粒度上限）
EVENT_NAME_MAP = {
    "For undergraduates, the summer student vacation begins on": "Summer vacation begins (UG)",
    "For taught postgraduates, the summer research period begins on": "Summer research period begins (PGT)",
}

COLLEGE_RE = r"College of (?:Arts and Law|Engineering and Physical Sciences|Life and Environmental Sciences|Medicine and Health|Social Sciences)"


class Birmingham(BaseParser):
    uni_code = UniCode.BHAM

    def program_catalog(self, page, res):
        # 课程搜索页是 JS 渲染抓不全（历史仅 14 个）；权威全量源是
        # /study/sitemap.xml 的 <loc>（702 个，实测 2026-07-05）
        if "sitemap" in page.url:
            for loc in page.soup.select("loc"):
                url = norm_ws(loc.get_text(strip=True))
                if re.search(COURSE_RE, url) and "/dubai/" not in url:
                    res.discovered.append(DiscoveredPage(
                        url=url, category=Category.PROGRAM_DETAIL))
            if not res.discovered:
                res.note("study/sitemap.xml 未解析出专业 URL（结构变了？）")
            return
        for url, title, _ in find_links(page, COURSE_RE):
            if "/dubai/" not in url:
                res.discovered.append(DiscoveredPage(
                    url=url, category=Category.PROGRAM_DETAIL, title=title or None))
        if not res.discovered:
            res.note("Birmingham 目录页未解析出课程详情链接")

    def program_detail(self, page, res):
        name = title_from(page, suffix_re=r"\s*-\s*University of Birmingham$")
        if not name:
            res.note("未解析出课程名称")
            return
        p = ProgramData(name_en=name, level="UG" if "/undergraduate/" in page.url else "PGT",
                        url=page.url, entry_year=_entry_year(page, self.entry_year))
        tiles = _tiles(page)
        p.ucas_code = tiles.get("UCAS code")
        p.campus = tiles.get("Campus")
        p.duration = tiles.get("Duration")
        p.entry_req_text = tiles.get("Entry requirements") or section_text(page, r"Entry requirements", limit=700)
        p.faculty = self.canon_faculty(page.txt, COLLEGE_RE)
        p.dept = _dept(page)
        p.tuition_home = fee_near(" ".join(tiles.values()) + "\n" + page.txt, ("UK/Ireland", "Home", "UK"))
        p.tuition_intl = fee_near(page.txt, ("International", "Overseas"))
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        self._modules(page, p)
        if p.tuition_intl is None:
            p.notes.append("静态页未稳定暴露国际学费")
        res.programs.append(p)

    def _modules(self, page, p):
        root = page.soup.find(id=re.compile("module", re.I))
        if not root:
            return
        for node in root.find_all(["a", "h3", "h4"]):
            title = norm_ws(node.get_text(" ", strip=True))
            if 6 <= len(title) <= 140 and not re.search(r"module information|optional|compulsory|fees|apply", title, re.I):
                href = page.abs(node["href"]) if node.name == "a" and node.get("href") else None
                # 只认手册域的课程链接；营销页课表区块里的杂链（博客/hub 在线
                # 学位站）曾被当课程链接登记出 5,078 个垃圾任务（2026-07-05）
                if href and "program-and-modules-handbook" not in href:
                    href = None
                p.modules.append(ModuleRef(name=title, url=href))

    # ---------------- 官方课程目录（Programmes & Modules Handbook）----------------
    # WebHandbooks servlet（探明 2026-07-05）：getSchoolList（52 院系）→
    # getProgramList（专业变体，含 FT/PT）→ getModuleList（模块名单：名称+代码
    # +详情链接）。会话态：须先按序访问 schoolList + 任一 programList（域级
    # prime 链在 yaml domains 配置）；院系名经 uaSchool 附加参数沿链传递
    # （servlet 容忍未知参数，实测）。只收名单，详情存链接不镜像。
    def module_catalog(self, page, res):
        from urllib.parse import parse_qs, quote, urlsplit
        q = parse_qs(urlsplit(page.url).query)
        action = (q.get("Action") or [""])[0]
        if action == "getSchoolList":
            for href, text in page.links(href_re=r"Action=getProgramList"):
                res.discovered.append(DiscoveredPage(
                    url=href, category=Category.MODULE_CATALOG,
                    title=f"{text} 专业列表（手册）"))
            if not res.discovered:
                res.note("手册学校列表未解析出院系链接")
            return
        if action == "getProgramList":
            school = (q.get("pgDdesc") or [""])[0]
            seen = set()
            for href, _t in page.links(href_re=r"Action=getModuleList"):
                if href in seen:
                    continue
                seen.add(href)
                res.discovered.append(DiscoveredPage(
                    url=f"{href}&uaSchool={quote(school)}",
                    category=Category.MODULE_CATALOG,
                    title=f"{school} 模块名单（手册）"))
            if not res.discovered:
                res.info(f"{school} 手册无专业模块链接（小院系可能确实没有）")
            return
        if action == "getModuleList":
            dept = (q.get("uaSchool") or [None])[0]
            for a in page.soup.select('a[href*="getModuleDetailsList"]'):
                aq = parse_qs(urlsplit(page.abs(a["href"])).query)
                subj = (aq.get("pgSubj") or [""])[0]
                crse = (aq.get("pgCrse") or [""])[0]
                name = norm_ws(a.get_text(" ", strip=True))
                # 每模块两个锚点（名称行 + 代码行），只取名称行；null 行跳过
                if subj in ("", "null") or not name or re.fullmatch(r"[0-9 ]+", name):
                    continue
                res.modules.append(ModuleData(
                    name_en=name, url=page.abs(a["href"]),
                    entry_year=self.entry_year, code=f"{subj} {crse}", dept=dept))
            if not res.modules:
                res.note("手册模块名单页无模块行")

    def term_dates(self, page, res):
        year = None
        for node in page.soup.find_all(["h2", "h3", "p", "li"]):
            text = norm_ws(node.get_text(" ", strip=True))
            m = re.search(r"\b(20\d{2})/(\d{2})\b", text)
            if node.name in ("h2", "h3") and m:
                year = f"{m.group(1)}/{m.group(2)}"
                continue
            start, end = date_range(text)
            if year and start:
                label = re.sub(r"\d{1,2}.*$", "", text).strip(" :-") or "Term date"
                label = EVENT_NAME_MAP.get(label, label)
                res.calendar.append(CalendarData(year, event_type(label, start), label, start, end))
        if not res.calendar:
            res.note("Birmingham academic year dates 未解析出日期")

    def ug_admissions(self, page, res):
        res.info("Birmingham UG 招生页作为参考页抓取")

    def pg_admissions(self, page, res):
        res.info("Birmingham PGT 招生页作为参考页抓取")

    def china_page(self, page, res):
        keyword_check(res, page, r"China", "Birmingham 中国专页")

    def faculty_list(self, page, res):
        if not re.search(COLLEGE_RE, page.txt):
            res.note("未匹配到 Birmingham College 名称")


def _tiles(page):
    out = {}
    for tile in page.soup.select(".course-tile, .course-tile-select"):
        label = tile.select_one(".course-tile__title, .course-tile-select__title")
        if not label:
            continue
        key = norm_ws(label.get_text(" ", strip=True)).rstrip(":")
        val = tile.select_one(".course-tile__value") or tile.select_one("option[selected]")
        text = norm_ws(val.get_text(" ", strip=True)) if val else ""
        if key and text:
            out[key] = text
    return out


def _entry_year(page, default):
    m = re.search(r"\b(20\d{2})\b", page.url)
    return m.group(1) if m else default


def _dept(page):
    m = re.search(r"\b(Birmingham Business School|School of [A-Z][A-Za-z &,\-]{3,80}|Department of [A-Z][A-Za-z &,\-]{3,80})\b", page.txt)
    if not m:
        return None
    # 正文散句里提到的院系名会连着谓语被吞进来（"Department of X was ranked..."
    # 曾造出 125 条散文院系行，2026-07-05）——逗号/谓语处截断，限长
    name = re.split(r",| (?:was|is|are|has|have|means|covers|enjoys|examines|"
                    r"stretches|offers|provides|at the|and (?:develop|work|clinical)|"
                    r"student-run|ranked|based)\b", norm_ws(m.group(1)))[0].strip()
    name = re.sub(r"\s+(?:and|in|to|of|the)$", "", name)
    return name if 8 <= len(name) <= 60 else None
