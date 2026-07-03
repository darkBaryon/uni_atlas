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

DB_NAME = "study_abroad"
MY_CNF = os.path.expanduser("~/.my.cnf")
