"""解析器框架：标准数据类 + Page 辅助类 + BaseParser 基类。

写一所新学校的解析器 = 建一个 BaseParser 子类：

    from parsers.base import BaseParser, ProgramData, DeadlineData

    class Sheffield(BaseParser):
        uni_code = "shef"

        def program_detail(self, page, res):   # 方法名 = source_pages.category
            p = ProgramData(name_en=page.h1(), level=..., url=page.url,
                            entry_year=self.entry_year)
            p.tuition_intl = page.money(r"Overseas[^\n]*\n£([\d,]+)")
            res.programs.append(p)

- 子类定义即自动注册（无需改任何注册表/__init__）；
- 类别方法只吃本地快照（page），不碰网络；
- 字段抓不到显式置 None，并 res.note() 说明（信息不存在要写清楚）。
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

PARSERS = {}   # (uni_code, category) -> fn(html, url) -> ParseResult

# 与 source_pages.category 对应；BaseParser 子类实现同名方法即注册
CATEGORIES = ("program_detail", "program_catalog", "module_catalog",
              "term_dates", "ug_admissions", "pg_admissions", "faculty_list",
              "language_req", "china_page", "deadlines", "fees",
              "staff_list", "research", "news", "other")


def register(uni_code, category):
    """函数式注册（BaseParser 之外的兜底用法）。"""
    def deco(fn):
        PARSERS[(uni_code, category)] = fn
        return fn
    return deco


def get_parser(uni_code, category):
    return PARSERS.get((uni_code, category))


# ---------------------------------------------------------------- 数据类
@dataclass
class DeadlineData:
    audience: str                     # all | international | home
    deadline_type: str                # application | equal_consideration | ...
    deadline_at: str                  # 'YYYY-MM-DD HH:MM:SS'
    entry_year: str
    note: Optional[str] = None


@dataclass
class ModuleRef:
    """专业页上的课程引用（只有名称/代码/链接，详情靠课程页任务补齐）。"""
    name: str
    code: Optional[str] = None
    url: Optional[str] = None
    module_type: str = "core"         # core | optional | elective


@dataclass
class ProgramData:
    name_en: str
    level: str                        # UG | PGT | PGR
    url: str
    entry_year: str
    ucas_code: Optional[str] = None
    duration: Optional[str] = None
    campus: Optional[str] = None
    faculty: Optional[str] = None
    dept: Optional[str] = None
    tuition_home: Optional[float] = None
    tuition_intl: Optional[float] = None
    currency: str = "GBP"
    fee_year_label: Optional[str] = None
    entry_req_text: Optional[str] = None
    language_band: Optional[str] = None    # UCL 式分级；无分级制的学校为 None
    ielts_overall: Optional[float] = None  # 直接给分的学校（如格拉斯哥）
    ielts_min_each: Optional[float] = None
    app_open_date: Optional[str] = None    # 'YYYY-MM-DD'
    deadlines: list = field(default_factory=list)     # [DeadlineData]
    modules: list = field(default_factory=list)       # [ModuleRef]
    notes: list = field(default_factory=list)


@dataclass
class ModuleData:
    name_en: str
    url: str
    entry_year: str
    code: Optional[str] = None
    credits: Optional[int] = None
    level: Optional[str] = None       # 'FHEQ Level 7' 等
    semester: Optional[str] = None
    leader: Optional[str] = None
    description: Optional[str] = None
    assessment: Optional[list] = None  # [{'weight': 75, 'type': 'Exam'}]
    prerequisites: Optional[str] = None
    notes: list = field(default_factory=list)


@dataclass
class CalendarData:
    academic_year: str                # '2025/26'
    event_type: str                   # teaching_period | exam_period | ...
    name: str
    start_date: str
    end_date: Optional[str] = None
    calendar_track: str = "standard"


@dataclass
class DiscoveredPage:
    """discover 任务的产出：写回 source_pages 的新任务行。"""
    url: str
    category: str
    title: Optional[str] = None
    note: Optional[str] = None
    crawl_freq: str = "monthly"
    fetch_method: str = "html"


@dataclass
class ParseResult:
    programs: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    calendar: list = field(default_factory=list)
    deadlines: list = field(default_factory=list)     # 校级
    discovered: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def note(self, msg):
        self.notes.append(msg)

    def counts(self):
        parts = [(len(self.programs), "专业"), (len(self.modules), "课程"),
                 (len(self.calendar), "校历"), (len(self.deadlines), "截止"),
                 (len(self.discovered), "新任务")]
        return ", ".join(f"{n} {label}" for n, label in parts if n)


# ---------------------------------------------------------------- 通用工具
DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%d/%m/%Y", "%Y-%m-%d")


def parse_date(s):
    """'20 Oct 2025' / '20 October 2025' 等 -> '2025-10-20'；解析不了返回 None。"""
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def money(s):
    """含 £ 金额的文本 -> float；没有返回 None。"""
    m = re.search(r"£\s*([\d,]+(?:\.\d{1,2})?)", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


class Page:
    """一张快照页的解析辅助：懒加载 soup/纯文本 + 常用提取器。"""

    def __init__(self, html, url):
        self.html = html
        self.url = url
        self._soup = None
        self._txt = None

    @property
    def soup(self):
        if self._soup is None:
            self._soup = BeautifulSoup(self.html, "html.parser")
        return self._soup

    @property
    def txt(self):
        """整页纯文本（\\n 分隔），正则字段提取都在它上面做。"""
        if self._txt is None:
            self._txt = self.soup.get_text("\n", strip=True)
        return self._txt

    def abs(self, href):
        return urljoin(self.url, href).split("#")[0]

    def h1(self):
        el = self.soup.find("h1")
        return norm_ws(el.get_text(strip=True)) if el else None

    def title_tail(self, sep=" - "):
        """<title> 的最后一段（格拉式页面的真实标题所在）。"""
        t = self.soup.title
        return t.get_text().split(sep)[-1].strip() if t else None

    def re(self, pattern, group=1, flags=0):
        """在纯文本上搜正则，返回捕获组（默认第 1 组）；无匹配返回 None。"""
        m = re.search(pattern, self.txt, flags)
        if not m:
            return None
        return m.group(group) if m.groups() else m.group(0)

    def kv(self, label, flags=0):
        """'标签:\\n值' 版式的取值：kv('Credit value') -> '15'。"""
        return self.re(label + r":?\s*\n([^\n]+)", flags=flags)

    def money(self, pattern=None, flags=0):
        """money(r'Overseas[^\\n]*\\n£([\\d,]+)')；不传 pattern 则全文找首个 £ 金额。"""
        if pattern is None:
            return money(self.txt)
        m = re.search(pattern, self.txt, flags)
        return float(m.group(1).replace(",", "")) if m else None

    def date(self, pattern, flags=0):
        """正则取到日期文本后走 parse_date。"""
        return parse_date(self.re(pattern, flags=flags))

    def links(self, css=None, href_re=None):
        """取链接 [(绝对URL, 文本)]，可按 CSS 选择器和/或 href 正则过滤，自动去重。"""
        scope = self.soup.select(css) if css else [self.soup]
        seen, out = set(), []
        for node in scope:
            for a in node.find_all("a", href=True):
                url = self.abs(a["href"])
                if href_re and not re.search(href_re, url):
                    continue
                if url in seen:
                    continue
                seen.add(url)
                out.append((url, norm_ws(a.get_text(strip=True))))
        return out


# ---------------------------------------------------------------- 基类
class BaseParser:
    """每校一个子类：声明 uni_code，实现与 category 同名的方法。

    方法签名: def <category>(self, page: Page, res: ParseResult) -> None
    子类定义即自动注册；解析中的异常由基类记日志并转为 res.note（页面级失败，
    不影响整轮——与 pipeline 的兜底一致，但日志里能看到堆栈）。
    """

    uni_code = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.uni_code:
            raise TypeError(f"{cls.__name__} 必须声明 uni_code")
        inst = cls()
        n = 0
        for cat in CATEGORIES:
            method = getattr(inst, cat, None)
            if callable(method):
                PARSERS[(cls.uni_code, cat)] = cls._wrap(inst, cat, method)
                n += 1
        logger.debug("注册解析器 %s: %d 个类别", cls.uni_code, n)

    @staticmethod
    def _wrap(inst, cat, method):
        def parse(html, url):
            res = ParseResult()
            page = Page(html, url)
            try:
                method(page, res)
            except Exception:
                logger.exception("[%s/%s] 解析异常: %s", inst.uni_code, cat, url[:80])
                res.note(f"解析异常（{cat}），详见日志")
            return res
        return parse

    # ---- 子类可用的公共属性/工具 ----
    @property
    def conf(self):
        """本校 YAML 配置（config/universities/<code>.yaml）；可能为 None。"""
        return config.uni(self.uni_code)

    @property
    def entry_year(self):
        u = self.conf
        return u.entry_year if u else config.DEFAULT_ENTRY_YEAR

    def canon_faculty(self, txt, pattern):
        """把正文里的院系提及规范化到 YAML faculties 官方清单（防句子片段污染）。

        pattern: 匹配院系提及的正则（如 r"School of [A-Z][A-Za-z ,&\\-]{3,70}"）。
        """
        u = self.conf
        if not u or not u.faculties:
            return None
        norm = lambda s: re.sub(r"\s+", " ", s.lower().replace(" and ", " & ")).strip()
        canon = {norm(k): k for k in u.faculties}
        for m in re.finditer(pattern, txt):
            cand = norm(m.group(0))
            for nk, name in canon.items():
                if cand == nk or cand.startswith(nk):
                    return name
        return None
