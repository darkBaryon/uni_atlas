"""UCL 解析器（选择器实测于 2026-07 试点）。

页面特点：
- 目录页 div.result-item 学位卡（链接 + span.search-results__dept 院系）；
- 专业页学费在 .study-mode 元素、含义看前置 dt/h4 标签；
- 语言要求为 Level 1-5 分级制（分数表在校级 language_req 页）；
- 课程（模块）代码可从 module-catalogue 链接尾部提取。
"""
import re

from parsers.base import BaseParser
from parsers.models import DeadlineData, DiscoveredPage, ModuleData, ModuleRef, ProgramData
from parsers.page import parse_date

MODULE_CODE_RE = re.compile(r"-([A-Z]{4}\d{4})/?$")


class UCL(BaseParser):
    uni_code = "ucl"

    # ---------------- 专业页 ----------------
    def program_detail(self, page, res):
        name = page.h1()
        if not name:
            res.note("页面无 h1 标题，可能非专业页")
            return
        p = ProgramData(name_en=name, url=page.url, entry_year=self.entry_year,
                        level="UG" if "/undergraduate/" in page.url else "PGT")

        # 学费/学制: .study-mode 元素 + 前置标签判断含义
        for el in page.soup.select(".study-mode"):
            prev = el.find_previous(["dt", "h4", "h5", "strong", "th"])
            label = prev.get_text(strip=True) if prev else ""
            val = el.get_text(strip=True)
            if "UK tuition" in label:
                p.tuition_home = _fee(val, p, "UK")
                m = re.search(r"\((\d{4}/\d{2})\)", label)
                p.fee_year_label = m.group(1) if m else None
            elif "Overseas tuition" in label:
                p.tuition_intl = _fee(val, p, "Overseas")
            elif label == "Duration" and not p.duration:
                p.duration = val
        if p.fee_year_label:                      # '2026/27' -> '2026'
            p.entry_year = p.fee_year_label.split("/")[0]
        else:
            m = re.search(r"-(\d{4})/?$", page.url)   # slug 尾部 '...-bsc-2026'
            p.entry_year = m.group(1) if m else p.entry_year

        # 语言等级 / 学位要求 / UCAS / 校区
        band = page.re(r"English language level for this (?:course|programme) is:?\n?\s*Level (\d)")
        p.language_band = f"level-{band}" if band else None
        p.entry_req_text = page.re(
            r"(?:minimum of an?|Normally a minimum of an?)\s+"
            r"([^.\n]*(?:class|degree|Honours)[^.\n]*)")
        if p.entry_req_text:
            p.entry_req_text = p.entry_req_text.strip()[:300]
        p.ucas_code = page.re(r"UCAS(?: course)? code\n?\s*([A-Z0-9]{4,5})")
        p.campus = page.re(r"(?:Campus|Location)\n([^\n]+)")

        # 申请窗口：签证/非签证双轨（PGT）+ UCAS Apply by（UG）
        self._deadlines(page, p)

        # 课程表：优先 module-catalogue 链接（带代码），退化到纯文本行
        self._modules(page, p)

        if p.tuition_intl is None and not p.modules:
            p.notes.append("学费与课程表均未解析出，页面结构可能已变，需人工核对")
        res.programs.append(p)

    def _deadlines(self, page, p):
        m = re.search(r"require a visa:\s*\n?(\d{1,2} \w{3,9} \d{4})\s*\n?–\s*\n?"
                      r"(\d{1,2} \w{3,9} \d{4})", page.txt)
        if m and "do not require" not in page.txt[max(0, m.start() - 40):m.start()]:
            p.app_open_date = parse_date(m.group(1))
            end = parse_date(m.group(2))
            if end:
                p.deadlines.append(DeadlineData(
                    "international", "application", end + " 17:00:00",
                    p.entry_year, "需签证申请者截止"))
        m = re.search(r"do not require a visa:\s*\n?(\d{1,2} \w{3,9} \d{4})\s*\n?–\s*\n?"
                      r"(\d{1,2} \w{3,9} \d{4})", page.txt)
        if m:
            end = parse_date(m.group(2))
            if end:
                p.deadlines.append(DeadlineData(
                    "home", "application", end + " 17:00:00",
                    p.entry_year, "无需签证申请者截止"))
        d = page.date(r"UCAS[^\n]*\n?\s*Apply by\s*\n?\s*(\d{1,2} \w+ \d{4})")
        if d:
            p.deadlines.append(DeadlineData(
                "all", "equal_consideration", d + " 18:00:00",
                p.entry_year, "UCAS 常规截止"))

    def _modules(self, page, p):
        for cls, mtype in (("prog-modules-mandatory", "core"),
                           ("prog-modules-optional", "optional")):
            for sec in page.soup.select(f".{cls}"):
                links = sec.select('a[href*="/module-catalogue/modules/"]')
                if links:
                    for a in links:
                        href = page.abs(a["href"])
                        mm = MODULE_CODE_RE.search(href)
                        p.modules.append(ModuleRef(
                            name=re.sub(r"\s+", " ", a.get_text(strip=True)),
                            code=mm.group(1) if mm else None,
                            url=href, module_type=mtype))
                    continue
                for line in sec.get_text("\n", strip=True).split("\n"):
                    mm = re.match(r"^(.{4,120}?)\s*\(([A-Z]{4}\d{4})\)\s*$", line)
                    if mm:
                        p.modules.append(ModuleRef(mm.group(1), mm.group(2),
                                                   module_type=mtype))
                    elif (re.match(r"^[A-Z][^.]{6,90}$", line)
                          and not re.search(r"module|credit|Students|You |The |All "
                                            r"|Please|Optional|Compulsory|For more", line)):
                        p.modules.append(ModuleRef(line, module_type=mtype))

    # ---------------- 目录页 ----------------
    def program_catalog(self, page, res):
        for item in page.soup.select("div.result-item"):
            a = item.find("a", href=True)
            if not a:
                continue
            href = page.abs(a["href"])
            if "/degrees/" not in href and "/taught-degrees/" not in href:
                continue
            dept_el = item.select_one("span.search-results__dept")
            res.discovered.append(DiscoveredPage(
                url=href, category="program_detail",
                title=re.sub(r"\s+", " ", a.get_text(strip=True)),
                note=dept_el.get_text(strip=True) if dept_el else None))
        nxt = page.soup.select_one('a[rel="next"], li.pager__item--next a')
        if nxt and nxt.get("href"):
            res.discovered.append(DiscoveredPage(
                url=page.abs(nxt["href"]), category="program_catalog",
                title="目录分页", crawl_freq="manual"))
        if not res.discovered:
            res.note("目录页未解析出学位卡（result-item），页面结构可能已变")

    # ---------------- 课程（模块）页 ----------------
    def module_catalog(self, page, res):
        if "/module-catalogue/modules/" not in page.url:
            res.note("module-catalogue 根页为搜索界面，课程任务由专业页链接自动登记")
            return
        name = page.h1()
        if not name:
            res.note("课程页无标题，跳过")
            return
        mm = MODULE_CODE_RE.search(page.url)
        mod = ModuleData(name_en=name, url=page.url, entry_year=self.entry_year,
                         code=mm.group(1) if mm else None)
        credits = page.kv(r"Credit value")
        mod.credits = int(credits) if credits and credits.isdigit() else None
        mod.level = page.re(r"(FHEQ Level \d+)")
        mod.leader = page.kv(r"Module leader")
        mod.semester = page.kv(r"(?:Intended t|T)eaching term") or page.kv(r"Term")
        mod.prerequisites = page.kv(r"(?:Module p|P)rerequisites?")

        # 考核占比：'75% Exam' 行；同一课程按多个 delivery 重复列出需去重
        seen, ass = set(), []
        for w, t in re.findall(r"\n(\d{1,3})%\s*\n?([A-Z][^\n%]{2,60})", page.txt):
            key = (int(w), t.strip().lower())
            if key not in seen:
                seen.add(key)
                ass.append({"weight": int(w), "type": t.strip()})
        mod.assessment = ass or None

        desc_el = page.soup.select_one(".module-description, .field--name-body")
        if desc_el:
            mod.description = desc_el.get_text("\n", strip=True)[:8000]
        else:
            m = re.search(r"\nDescription\n(.{100,8000}?)(?:\nKey information\n|"
                          r"\nAssessment\n|\nOther information\n|$)", page.txt, re.S)
            mod.description = m.group(1).strip() if m else None
        if not mod.description:
            mod.notes.append("未解析出大纲正文")
        if mod.credits is None:
            mod.notes.append("未解析出学分")
        res.modules.append(mod)


def _fee(val, p, label):
    from parsers.page import money
    v = money(val)
    if v is None and val:
        p.notes.append(f"{label} 学费非标准格式，原文: {val[:200]}")
    return v
