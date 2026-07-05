"""抓取器包：对外只暴露 fetch_tasks 入口 + 结果协议（FetchKind/FetchResult）。

内部分工：
- core.py    编排（域并发/限速/退避/分类/消费线程）
- methods.py 按 fetch_method 发请求（GET/POST/预热/拿票分派）
- waf.py     WAF 拿票（浏览器旁路，仅标了 token 的域用）
- _util.py   共享 URL 助手
"""
from fetcher.core import FetchKind, FetchResult, fetch_tasks  # noqa: F401

__all__ = ["fetch_tasks", "FetchKind", "FetchResult"]
