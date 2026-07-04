"""声明式通用解析器：YAML `generic:` 段驱动，新校零 Python 接入。

与 common.py 的分工（勿混淆）：
- common.py  = 提取函数库（fee_near/ielts/...），专属解析器和本文件**都**调用；
- generic.py = 一个完整的解析器实现，服务「只有 YAML、没有 <code>.py」的学校。

10 校实战结论:英国大学官网共性远大于个性——目录页 = 一批匹配某 URL 模式
的链接；专业页 = 学费(£ 靠近 Home/Overseas 标签)、雅思、学制、UCAS code、
Entry requirements 区块。个性只剩 URL 模式和标签措辞，放 YAML 即可：

    generic:
      catalog:
        link_re: "/courses/2026/[a-z0-9-]+/?$"   # 必填：专业页 URL 特征
        scope_css: "main"                         # 选填：限定搜索范围
      detail:                                     # 全部选填，缺省用 10 校高频值
        name_source: title_tail    # 默认 h1
        pg_url_re: "/masters/"
        fee_intl_labels: ["Overseas students"]
        fee_home_labels: ["UK students"]
        entry_req_heading: "Entry requirements"
        deadline_label: "Application deadline"

YAML 键有拼写校验（GenericSpec，未知键导入时报错——与 UniCode 同原则）。
验收照旧：./run.sh check <code>——覆盖率不达标再降级写专属解析器。
"""
import logging
import re
from dataclasses import dataclass, fields

import config
from config.codes import Category
from parsers.base import BaseParser, get_parser
from parsers.models import DeadlineData, DiscoveredPage, ProgramData
from parsers.page import parse_date
from parsers.uk.common import fee_near, first, ielts, section_text

logger = logging.getLogger(__name__)

# 缺省措辞/模式：10 校观察的高频值（长的在前，先精确后宽泛）。
# 这些是英国经验，所以住在 parsers/uk/ 而不是 config 层。
FEE_INTL_LABELS = ["International & EU", "Overseas students", "International students",
                   "Overseas fee", "International fee", "Overseas", "International"]
FEE_HOME_LABELS = ["Home & RUK", "UK students", "Home students", "Home fee",
                   "Home (UK)", "Home"]
PG_URL_RE = r"/postgraduate|/masters|/taught|/pgt|-msc\b|-ma\b"
ENTRY_REQ_HEADING = (r"Entry requirements?|Academic requirements?|Qualifications|"
                     r"Academic entry qualification overview|Typical (?:A-level )?offer")
ENTRY_REQ_STOP = (r"English language|Fees|How to apply|Application and selection|"
                  r"Programme structure")
FACULTY_RE = (r"((?:Adam Smith Business School|(?:School|Faculty|College|Department)"
              r" of [A-Z][A-Za-z ,&\-]{3,70}))")
MIN_NAME_LEN = 3          # 短于此的"专业名"视为解析失败（如空 h1 抓到装饰字符）


def _from_dict(cls, raw, where):
    """dict -> dataclass，未知键立刻报错（拼错不允许静默落默认值）。"""
    raw = raw or {}
    known = {f.name for f in fields(cls)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"{where} 含未知键 {sorted(unknown)}（合法: {sorted(known)}）")
    return cls(**raw)


@dataclass
class CatalogSpec:
    link_re: str | None = None     # 必填；缺省时目录页解析直接报备注
    scope_css: str | None = None


@dataclass
class DetailSpec:
    name_source: str = "h1"        # h1 | title_tail
    pg_url_re: str = PG_URL_RE
    fee_intl_labels: list | None = None
    fee_home_labels: list | None = None
    entry_req_heading: str = ENTRY_REQ_HEADING
    deadline_label: str | None = None


@dataclass
class GenericSpec:
    catalog: CatalogSpec
    detail: DetailSpec

    @classmethod
    def parse(cls, raw, uni_code):
        raw = raw or {}
        unknown = set(raw) - {"catalog", "detail"}
        if unknown:
            raise ValueError(f"{uni_code} 的 generic 段含未知键 {sorted(unknown)}")
        return cls(
            catalog=_from_dict(CatalogSpec, raw.get("catalog"), f"{uni_code}.generic.catalog"),
            detail=_from_dict(DetailSpec, raw.get("detail"), f"{uni_code}.generic.detail"))


class GenericUK(BaseParser):
    """不直接注册；由 register_for_configured() 按 YAML 动态派生每校子类。"""
    abstract = True
    _spec: GenericSpec | None = None

    @property
    def spec(self) -> GenericSpec:
        cls = type(self)
        if cls._spec is None:
            raw = self.conf.generic if self.conf else None
            cls._spec = GenericSpec.parse(raw, self.uni_code)
        return cls._spec

    # ---------------- 目录页 ----------------
    def program_catalog(self, page, res):
        cat = self.spec.catalog
        if not cat.link_re:
            res.note("generic.catalog.link_re 未配置，目录无法展开")
            return
        for url, text in page.links(cat.scope_css, cat.link_re):
            if url.rstrip("/") == page.url.rstrip("/"):
                continue
            res.discovered.append(DiscoveredPage(
                url=url, category=Category.PROGRAM_DETAIL, title=text or None))
        nxt = page.soup.select_one('a[rel="next"], .pager-next a, li.next a')
        if nxt and nxt.get("href"):
            res.discovered.append(DiscoveredPage(
                url=page.abs(nxt["href"]), category=Category.PROGRAM_CATALOG,
                title="目录分页", crawl_freq="manual"))
        if not res.discovered:
            res.note(f"目录页未匹配到 {cat.link_re} 链接，页面结构需人工核对")

    # ---------------- 专业页 ----------------
    def program_detail(self, page, res):
        d = self.spec.detail
        name = (page.title_tail() if d.name_source == "title_tail"
                else page.h1() or page.title_tail())
        if not name or len(name) < MIN_NAME_LEN:
            res.note("未解析出专业名（h1/title 均空），可能非专业页")
            return
        is_pg = bool(re.search(d.pg_url_re, page.url, re.I))
        p = ProgramData(name_en=name, level="PGT" if is_pg else "UG",
                        url=page.url, entry_year=self.entry_year)

        p.tuition_intl = fee_near(page.txt, d.fee_intl_labels or FEE_INTL_LABELS)
        p.tuition_home = fee_near(page.txt, d.fee_home_labels or FEE_HOME_LABELS)
        p.ielts_overall, p.ielts_min_each = ielts(page.txt)
        p.duration = first(page.txt,
                           r"Duration:?\s*\n\s*([^\n]{2,60})",
                           r"\b(\d+ (?:years?|months?)(?:,? full[- ]time| part[- ]time)?)\b")
        p.ucas_code = first(page.txt, r"UCAS(?: course)? code:?\s*\n?\s*([A-Z0-9]{4,5})\b")
        p.entry_req_text = section_text(page, d.entry_req_heading, ENTRY_REQ_STOP, 400)
        p.dept = self.canon_faculty(page.txt, FACULTY_RE)

        if d.deadline_label:
            dl = parse_date(first(page.txt, re.escape(d.deadline_label) +
                                  r":?\s*\n?\s*(\d{1,2} \w+ \d{4})"))
            if dl:
                p.deadlines.append(DeadlineData(
                    "all", "application", dl + " 23:59:00",
                    p.entry_year, f"{d.deadline_label}（通用解析）"))

        if p.tuition_intl is None and is_pg:
            p.notes.append("通用解析器未取到国际学费，如批量缺失需写专属解析器")
        res.programs.append(p)


def register_for_configured():
    """「YAML 有 generic 段且无专属解析器」的学校 → 动态派生子类完成注册。

    type(...) 建类等价于 `class GenericUK_<code>(GenericUK): uni_code = <code>`，
    定义即触发 BaseParser.__init_subclass__ 的注册与校验；同时立即解析
    GenericSpec，让 YAML 拼写错误在导入时暴露而不是首次抓取时。
    """
    for code, u in config.all_unis().items():
        if not u.generic:
            continue
        if get_parser(code, Category.PROGRAM_DETAIL):
            logger.debug("%s 已有专属解析器，generic 段忽略", code)
            continue
        spec = GenericSpec.parse(u.generic, code)   # 导入时验证 YAML 键
        type(f"GenericUK_{code}", (GenericUK,), {"uni_code": code, "_spec": spec})
        logger.info("通用解析器接管 %s（YAML 声明式）", code)
