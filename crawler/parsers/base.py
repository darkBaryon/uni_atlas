"""解析器基类与注册表。

写一所新学校的解析器 = 建一个 BaseParser 子类：

    from parsers.base import BaseParser
    from parsers.models import ProgramData

    class Sheffield(BaseParser):
        uni_code = "shef"

        def program_detail(self, page, res):   # 方法名 = source_pages.category
            res.programs.append(ProgramData(...))

子类定义即自动注册（无需改任何注册表/__init__）。
"""
import logging
import re

import config
from parsers.models import ParseResult
from parsers.page import Page

logger = logging.getLogger(__name__)

# 与 source_pages.category 对应；BaseParser 子类实现同名方法即注册
CATEGORIES = ("program_detail", "program_catalog", "module_catalog",
              "term_dates", "ug_admissions", "pg_admissions", "faculty_list",
              "language_req", "china_page", "deadlines", "fees",
              "staff_list", "research", "news", "other")

PARSERS = {}   # (uni_code, category) -> fn(html, url) -> ParseResult


def register(uni_code, category):
    """函数式注册（BaseParser 之外的兜底用法）。"""
    def deco(fn):
        PARSERS[(uni_code, category)] = fn
        return fn
    return deco


def get_parser(uni_code, category):
    return PARSERS.get((uni_code, category))


class BaseParser:
    """每校一个子类：声明 uni_code，实现与 category 同名的方法。

    方法签名: def <category>(self, page: Page, res: ParseResult) -> None
    子类定义即自动注册；解析中的异常由基类记日志并转为 res.note（页面级失败，
    不影响整轮——与 pipeline 的兜底一致，但日志里能看到堆栈）。
    """

    uni_code: str | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("abstract"):   # 中间基类（如 GenericUK）不注册
            return
        if not cls.uni_code:
            raise TypeError(f"{cls.__name__} 必须声明 uni_code")
        # uni_code 是指向配置层的外键（权威定义在 config/universities/*.yaml 的
        # code 字段），导入时即校验——拼错立刻炸，而不是运行时默默查不到解析器
        if config.uni(cls.uni_code) is None:
            raise TypeError(
                f"{cls.__name__}.uni_code={cls.uni_code!r} 在 config/universities/"
                f" 中不存在（已知: {sorted(config.all_unis())}）——检查拼写或先建 YAML")
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
        def norm(s):
            return re.sub(r"\s+", " ", s.lower().replace(" and ", " & ")).strip()

        canon = {norm(k): k for k in u.faculties}
        for m in re.finditer(pattern, txt):
            cand = norm(m.group(0))
            for nk, name in canon.items():
                if cand == nk or cand.startswith(nk):
                    return name
        return None
