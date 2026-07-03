"""通用英国大学解析器：YAML 声明式驱动，新校零 Python 接入。

10 校实战沉淀的经验：英国大学官网的共性远大于个性——
目录页 = 一批匹配某 URL 模式的链接；专业页 = 学费(£ 靠近 Home/Overseas
标签)、雅思、学制、UCAS code、Entry requirements 区块。个性只剩下
URL 模式和标签措辞，这些放 YAML 就够了。

启用方式：学校 YAML 加 generic 段（且不存在 parsers/<code>.py 时自动注册）：

    generic:
      catalog:
        link_re: "/courses/2026/[a-z0-9-]+/?$"   # 必填：专业页 URL 特征
        scope_css: "main"                         # 选填：限定搜索范围
      detail:                                     # 全部选填，有默认值
        name_source: h1            # h1(默认) | title_tail
        pg_url_re: "/masters/"     # URL 判级正则（默认见 PG_URL_RE）
        fee_intl_labels: ["Overseas students"]
        fee_home_labels: ["UK students"]
        deadline_label: "Application deadline"    # kv 版式的截止日期

验收照旧：./run.sh check <code>——覆盖率不达标再降级写专属解析器。
"""
import logging
import re

import config
from parsers.base import (BaseParser, DeadlineData, DiscoveredPage,
                          ProgramData, get_parser, parse_date)
from parsers.uk_common import fee_near, first, ielts, section_text

logger = logging.getLogger(__name__)

# 默认标签/模式：按 10 校观察到的高频措辞排序（长的在前，先精确后宽泛）
FEE_INTL_LABELS = ["International & EU", "Overseas students", "International students",
                   "Overseas fee", "International fee", "Overseas", "International"]
FEE_HOME_LABELS = ["Home & RUK", "UK students", "Home students", "Home fee",
                   "Home (UK)", "Home"]
PG_URL_RE = r"/postgraduate|/masters|/taught|/pgt|-msc\b|-ma\b"
FACULTY_RE = (r"((?:Adam Smith Business School|(?:School|Faculty|College|Department)"
              r" of [A-Z][A-Za-z ,&\-]{3,70}))")


class GenericUK(BaseParser):
    """不直接注册；由 register_for_configured() 按 YAML 动态派生子类。"""
    abstract = True

    @property
    def g(self):
        return (self.conf.generic if self.conf else None) or {}

    # ---------------- 目录页 ----------------
    def program_catalog(self, page, res):
        cat = self.g.get("catalog") or {}
        link_re = cat.get("link_re")
        if not link_re:
            res.note("generic.catalog.link_re 未配置，目录无法展开")
            return
        for url, text in page.links(cat.get("scope_css"), link_re):
            if url.rstrip("/") == page.url.rstrip("/"):
                continue
            res.discovered.append(DiscoveredPage(
                url=url, category="program_detail", title=text or None))
        nxt = page.soup.select_one('a[rel="next"], .pager-next a, li.next a')
        if nxt and nxt.get("href"):
            res.discovered.append(DiscoveredPage(
                url=page.abs(nxt["href"]), category="program_catalog",
                title="目录分页", crawl_freq="manual"))
        if not res.discovered:
            res.note(f"目录页未匹配到 {link_re} 链接，页面结构需人工核对")

    # ---------------- 专业页 ----------------
    def program_detail(self, page, res):
        d = self.g.get("detail") or {}
        name = (page.title_tail() if d.get("name_source") == "title_tail"
                else page.h1() or page.title_tail())
        if not name or len(name) < 3:
            res.note("未解析出专业名（h1/title 均空），可能非专业页")
            return
        is_pg = bool(re.search(d.get("pg_url_re", PG_URL_RE), page.url, re.I))
        p = ProgramData(name_en=name, level="PGT" if is_pg else "UG",
                        url=page.url, entry_year=self.entry_year)

        p.tuition_intl = fee_near(page.txt, d.get("fee_intl_labels", FEE_INTL_LABELS))
        p.tuition_home = fee_near(page.txt, d.get("fee_home_labels", FEE_HOME_LABELS))
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        p.duration = first(page.txt,
                           r"Duration:?\s*\n\s*([^\n]{2,60})",
                           r"\b(\d+ (?:years?|months?)(?:,? full[- ]time| part[- ]time)?)\b")
        p.ucas_code = first(page.txt, r"UCAS(?: course)? code:?\s*\n?\s*([A-Z0-9]{4,5})\b")
        # 标题措辞按 10 校观察列高频变体；yaml detail.entry_req_heading 可覆盖
        p.entry_req_text = section_text(
            page,
            d.get("entry_req_heading",
                  r"Entry requirements?|Academic requirements?|Qualifications|"
                  r"Academic entry qualification overview|Typical (?:A-level )?offer"),
            r"English language|Fees|How to apply|Application and selection|Programme structure",
            400)
        p.dept = self.canon_faculty(page.txt, FACULTY_RE)

        label = d.get("deadline_label")
        if label:
            dl = parse_date(first(page.txt, re.escape(label) +
                                  r":?\s*\n?\s*(\d{1,2} \w+ \d{4})"))
            if dl:
                p.deadlines.append(DeadlineData(
                    "all", "application", dl + " 23:59:00",
                    p.entry_year, f"{label}（通用解析）"))

        if p.tuition_intl is None and is_pg:
            p.notes.append("通用解析器未取到国际学费，如批量缺失需写专属解析器")
        res.programs.append(p)


def register_for_configured():
    """给「YAML 有 generic 段且无专属解析器」的学校动态派生并注册子类。"""
    for code, u in config.all_unis().items():
        if not u.generic:
            continue
        if get_parser(code, "program_detail"):
            logger.debug("%s 已有专属解析器，generic 段忽略", code)
            continue
        type(f"GenericUK_{code}", (GenericUK,), {"uni_code": code})
        logger.info("通用解析器接管 %s（YAML 声明式）", code)
