"""配置层：全局默认 + 按校 YAML。

- 全局默认（限速兜底/UA/路径/退避/优先级）在本文件；
- 每所学校一个 YAML：config/universities/<code>.yaml，
  内容包括域名限速、申请季、抓取范围、入口页种子（见 ucl.yaml 样例）。
"""
import functools
import glob
import os
from typing import NamedTuple

import yaml

# crawler/config/__init__.py -> 仓库根
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAP_ROOT = os.path.join(ROOT, "snapshots")   # snapshots/{uni_code}/{category}/
_UNI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "universities")

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 域抓取策略兜底；各校 YAML 的 domains 可按域覆盖，写法：
#   domains:
#     www.example.ac.uk: {interval: 3.0, concurrency: 1}
# interval = 同域两次请求发起的最小间隔（秒），实际间隔 += random(0, JITTER)；
# concurrency = 域内并发 worker 数，仅对实测无限流的域调大（>1 即牺牲礼貌换速度）。
DEFAULT_INTERVAL = 3.0
DEFAULT_CONCURRENCY = 1
JITTER = 1.0


class DomainPolicy(NamedTuple):
    interval: float
    concurrency: int
    prime: tuple = ()   # 会话预热 URL（老式有状态站点：每次运行先按序 GET 一遍）

MAX_DOMAINS = 10              # 同时并发的域名数上限
TIMEOUT = 30                  # 单请求超时（秒）
WAF_SOLVE_TIMEOUT = 40        # 浏览器打开 WAF 页的导航超时（秒）
WAF_SOLVE_WAIT = 180          # 等用户手动过 CAPTCHA 的最长时间（秒）
CF_BACKOFFS = [30, 60, 120]   # 反爬挑战退避序列；用尽后放弃本轮
# 各家 WAF 挑战页标记：Cloudflare 三种 + Imperva/Distil + AWS WAF（UQ）
# （墨尔本 handbook 实测 2026-07：连发 ~6 请求触发，冷却后自动恢复）
CF_MARKERS = ("Just a moment", "cf-challenge", "Checking your browser",
              "Pardon Our Interruption", "Human Verification")

DEFAULT_ENTRY_YEAR = "2026"   # 学校 YAML 未指定申请季时的默认值

from config.codes import Category  # noqa: E402  常量层无外部依赖，置底避免环

# 抓取优先级：越靠前越先抓（申请决策直接依赖的排前，课程大纲类殿后）
CATEGORY_PRIORITY = [
    Category.DEADLINES, Category.TERM_DATES, Category.UG_ADMISSIONS,
    Category.PG_ADMISSIONS, Category.LANGUAGE_REQ, Category.CHINA_PAGE,
    Category.FEES, Category.PROGRAM_DETAIL, Category.PROGRAM_CATALOG,
    Category.FACULTY_LIST, Category.MODULE_CATALOG, Category.STAFF_LIST,
    Category.RESEARCH, Category.NEWS, Category.OTHER,
]

DB_NAME = "study_abroad"
MY_CNF = os.path.expanduser("~/.my.cnf")


class UniConfig:
    """一所学校的配置视图（来自 config/universities/<code>.yaml）。"""

    def __init__(self, data, path):
        self.path = path
        self.code = data["code"]
        self.name = data.get("name")
        self.name_zh = data.get("name_zh")
        self.website = data.get("website")
        self.country = data.get("country")
        self.city = data.get("city")
        self.entry_year = str(data.get("entry_year", DEFAULT_ENTRY_YEAR))
        self.domains = {k: _parse_domain_policy(k, v)
                        for k, v in (data.get("domains") or {}).items()}
        scope = data.get("scope") or {}
        # focus_depts=None 表示不限院系（全校专业页都自动抓）
        self.focus_depts = scope.get("focus_depts")
        self.crawl_module_details = bool(scope.get("crawl_module_details", False))
        self.seed_pages = data.get("seed_pages") or []
        # 数据体检阈值覆盖（audit.py；键见 audit.DEFAULTS）
        self.expect = data.get("expect") or {}
        # 官方院系清单 {英文名: 中文名}：解析器用来规范化院系提及，loader 用来填 name_zh
        self.faculties = data.get("faculties") or {}
        # 页面叫法 -> 官方名的别名映射（如 UCL 目录页把计算机系写作 'Computer Science'）
        self.faculty_alias = data.get("faculty_alias") or {}
        # 人工整理层：专业 slug -> 官方院系名（页面无归属信号时的最后手段）
        self.faculty_overrides = data.get("faculty_overrides") or {}
        # 通用解析器的声明式配置（parsers/generic.py）；无专属解析器时凭它接管
        self.generic = data.get("generic")


def _parse_domain_policy(domain, v):
    if not isinstance(v, dict) or "interval" not in v:
        raise ValueError(
            f"domains.{domain} 须写成 {{interval: 秒, concurrency: N}} 形式，实际: {v!r}")
    return DomainPolicy(float(v["interval"]),
                        int(v.get("concurrency", DEFAULT_CONCURRENCY)),
                        tuple(v.get("prime", ())))


def _merge(base, over):
    """默认层与学校层合并：dict 逐键深并，其余类型学校层直接覆盖。"""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@functools.cache
def all_unis():
    """code -> UniConfig，递归装载 config/universities/**/*.yaml。

    目录 = 国家层；默认层按链合并：全局 _defaults.yaml → 国家目录
    _defaults.yaml → 学校文件（下划线开头的文件不算学校）。
    """
    global_defaults = {}
    gpath = os.path.join(_UNI_DIR, "_defaults.yaml")
    if os.path.exists(gpath):
        global_defaults = _load_yaml(gpath)
    out = {}
    for path in sorted(glob.glob(os.path.join(_UNI_DIR, "**", "*.yaml"),
                                 recursive=True)):
        if os.path.basename(path).startswith("_"):
            continue
        defaults = global_defaults
        cpath = os.path.join(os.path.dirname(path), "_defaults.yaml")
        if os.path.dirname(path) != _UNI_DIR and os.path.exists(cpath):
            defaults = _merge(global_defaults, _load_yaml(cpath))
        data = _load_yaml(path)
        if "code" not in data:
            raise ValueError(f"{path} 缺少 code 字段")
        out[data["code"]] = UniConfig(_merge(defaults, data), path)
    return out


def uni(code):
    """某校配置；没有 YAML 的学校返回 None（按全局默认处理）。"""
    return all_unis().get(code)


def domain_policy(domain):
    """域抓取策略（间隔+并发）：先查各校 YAML 的 domains 覆盖，否则全局兜底。"""
    for u in all_unis().values():
        if domain in u.domains:
            return u.domains[domain]
    return DomainPolicy(DEFAULT_INTERVAL, DEFAULT_CONCURRENCY, ())
