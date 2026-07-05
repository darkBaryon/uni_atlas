"""抓取方法分派：按 task.fetch_method 决定怎么"发请求"（含一次性会话预热）。

与 core 的分工：本文件只管"如何发出一个请求"，返回 async 上下文管理器
（进入后得到响应对象）；响应分类、限速、重试、并发都在 core。
新增抓取方式 = 在 send() 加一个分支（简单）或引一个方法模块（复杂，如 browser）。
"""
import config
from config.codes import FetchMethod
from fetcher import browser
from fetcher._util import domain

_PRIMED: set[str] = set()   # 已完成一次性预热的域（aiohttp 系）


async def _prime(session, task):
    """每域一次的 aiohttp 会话预热：配置声明的 prime 链、portlet render.uP。"""
    dom = domain(task.url)
    if dom in _PRIMED:
        return
    for url in config.domain_policy(dom).prime:        # 配置声明的会话预热链
        async with session.get(url, allow_redirects=True):
            pass
    if task.fetch_method == FetchMethod.PORTLET_POST:  # uPortal 固定预热 render.uP
        url = task.url.split("/action.uP")[0] + "/render.uP"
        async with session.get(url, allow_redirects=True):
            pass
    _PRIMED.add(dom)


async def send(session, task):
    """按方法返回一个 async 上下文管理器（core 用 `async with await send(...)`）。"""
    if task.fetch_method == FetchMethod.CDP:
        return browser.send(task.url)          # 交互式浏览器会话，自带过 CAPTCHA
    await _prime(session, task)                # 仅 aiohttp 系方法需要预热
    if task.fetch_method == FetchMethod.PORTLET_POST:
        return session.post(task.url, allow_redirects=True)
    return session.get(task.url, allow_redirects=True)
