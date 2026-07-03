"""配置层：全局默认 + 按校 YAML。

- 全局默认（限速兜底/UA/路径/退避/优先级）在本文件；
- 每所学校一个 YAML：config/universities/<code>.yaml，
  内容包括域名限速、申请季、抓取范围、入口页种子（见 ucl.yaml 样例）。
"""
import functools
import glob
import os

import yaml

# crawler/config/__init__.py -> 仓库根
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAP_ROOT = os.path.join(ROOT, "snapshots")   # snapshots/{uni_code}/{category}/
_UNI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "universities")

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 域内请求间隔兜底（秒）；各校 YAML 的 domains 可按域覆盖。
# 实际间隔 = interval + random(0, JITTER)
DEFAULT_INTERVAL = 3.0
JITTER = 1.0

MAX_DOMAINS = 10              # 同时并发的域名数上限
TIMEOUT = 30                  # 单请求超时（秒）
CF_BACKOFFS = [30, 60, 120]   # Cloudflare 挑战退避序列；用尽后放弃本轮
CF_MARKERS = ("Just a moment", "cf-challenge", "Checking your browser")

DEFAULT_ENTRY_YEAR = "2026"   # 学校 YAML 未指定申请季时的默认值

# 抓取优先级：越靠前越先抓（申请决策直接依赖的排前，课程大纲类殿后）
CATEGORY_PRIORITY = [
    "deadlines", "term_dates", "ug_admissions", "pg_admissions",
    "language_req", "china_page", "fees", "program_detail",
    "program_catalog", "faculty_list", "module_catalog",
    "staff_list", "research", "news", "other",
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
        self.domains = {k: float(v) for k, v in (data.get("domains") or {}).items()}
        scope = data.get("scope") or {}
        # focus_depts=None 表示不限院系（全校专业页都自动抓）
        self.focus_depts = scope.get("focus_depts")
        self.crawl_module_details = bool(scope.get("crawl_module_details", False))
        self.seed_pages = data.get("seed_pages") or []
        # 官方院系清单 {英文名: 中文名}：解析器用来规范化院系提及，loader 用来填 name_zh
        self.faculties = data.get("faculties") or {}


@functools.lru_cache(maxsize=None)
def all_unis():
    """code -> UniConfig，装载 config/universities/ 下全部 YAML。"""
    out = {}
    for path in sorted(glob.glob(os.path.join(_UNI_DIR, "*.yaml"))):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "code" not in data:
            raise ValueError(f"{path} 缺少 code 字段")
        out[data["code"]] = UniConfig(data, path)
    return out


def uni(code):
    """某校配置；没有 YAML 的学校返回 None（按全局默认处理）。"""
    return all_unis().get(code)


def domain_interval(domain):
    """域内请求间隔：先查各校 YAML 的 domains 覆盖，否则全局兜底。"""
    for u in all_unis().values():
        if domain in u.domains:
            return u.domains[domain]
    return DEFAULT_INTERVAL
