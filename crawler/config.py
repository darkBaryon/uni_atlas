"""爬虫全局配置：限速 / 重试 / 路径 / UA。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP_ROOT = os.path.join(ROOT, "snapshots")   # snapshots/{uni_code}/{category}/

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 域内请求间隔（秒），实际间隔 = interval + random(0, JITTER)
DEFAULT_INTERVAL = 3.0
JITTER = 1.0
DOMAIN_INTERVALS = {          # 按域覆盖
    "www.ucl.ac.uk": 3.0,
}

MAX_DOMAINS = 10              # 同时并发的域名数上限
TIMEOUT = 30                  # 单请求超时（秒）
CF_BACKOFFS = [30, 60, 120]   # Cloudflare 挑战退避序列；用尽后放弃本轮
CF_MARKERS = ("Just a moment", "cf-challenge", "Checking your browser")

DEFAULT_ENTRY_YEAR = "2026"   # 页面未标注申请季时的默认值

# ---- 抓取范围（核心数据的定义）----
# 只备份申请决策需要的数据，不做全站镜像：
# 校级关键页 + 关注院系的专业页自动抓；范围外的页面照常登记进任务表，
# 但 crawl_freq='manual'（--due 不会选中，需要时可定向抓）。
FOCUS_DEPTS = {
    "ucl": ["Computer Science", "School of Management"],
}
CRAWL_MODULE_DETAILS = False  # 模块详情页（大纲/考核）默认不抓，专业页自带模块名单

# 抓取优先级：越靠前越先抓（申请决策直接依赖的排前，课程大纲类殿后）
CATEGORY_PRIORITY = [
    "deadlines", "term_dates", "ug_admissions", "pg_admissions",
    "language_req", "china_page", "fees", "program_detail",
    "program_catalog", "faculty_list", "module_catalog",
    "staff_list", "research", "news", "other",
]

DB_NAME = "study_abroad"
MY_CNF = os.path.expanduser("~/.my.cnf")
