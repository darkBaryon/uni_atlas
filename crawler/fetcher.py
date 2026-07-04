"""抓取器：域名级并行 + 域内串行限速 + Cloudflare 退避。

对外只有一个入口 fetch_tasks(tasks, handle)：
tasks 按域名分队列，每域一个 worker 串行抓取（interval + 抖动），
域间并发（上限 MAX_DOMAINS）。每个结果同步回调 handle(result)。
"""
import asyncio
import random
from collections import deque
from enum import Enum
from http import HTTPStatus
from urllib.parse import urlsplit

import aiohttp

import config
from config.codes import FetchMethod


class FetchKind(str, Enum):
    """抓取结果分类——fetcher 与 pipeline 之间的协议，勿用裸字符串比较。"""
    OK = "ok"                    # 200，正文可用
    CLOUDFLARE = "cloudflare"    # 反爬挑战 / 429 限流（域内退避重试后仍未过）
    TRANSIENT = "transient"      # 5xx 瞬时错误（fetcher 内部重试一次，不外泄）
    DEAD = "dead"                # 404，任务标 dead
    MOVED = "moved"              # 301/302 跨页，登记新地址
    ERROR = "error"              # 其他失败（超时/连接错误/非 200）

    __str__ = str.__str__


class FetchResult:
    def __init__(self, task, kind: FetchKind, http_status=None, body=b"",
                 final_url=None, note=None):
        self.task = task
        self.kind = kind
        self.http_status = http_status
        self.body = body
        self.final_url = final_url
        self.note = note


def _domain(url):
    return urlsplit(url).netloc.lower()


def _same_page(a, b):
    """301 到 https/斜杠/加 www 等价页不算搬家。"""
    def host(s):
        return s.netloc.lower().removeprefix("www.")

    def path(s):
        return (s.path.rstrip("/") or "/") + ("?" + s.query if s.query else "")

    sa, sb = urlsplit(a), urlsplit(b)
    return host(sa) == host(sb) and path(sa) == path(sb)


def _is_cloudflare(status, text_head):
    if (status in (HTTPStatus.FORBIDDEN, HTTPStatus.SERVICE_UNAVAILABLE)
            and any(m in text_head for m in config.CF_MARKERS)):
        return True
    return any(m in text_head for m in config.CF_MARKERS)


_PRIMED: set[str] = set()   # portlet_post 已预热的域（GET render.uP 建会话 cookie）


async def _request(session, task):
    """按 fetch_method 发请求。portlet_post: uPortal 的 cookiecheck 302 会把
    POST 变 GET 丢参数，须先 GET 同 portlet 的 render.uP 预热（每域一次），
    之后参数全在任务 URL query 里 POST 即可（实测 2026-07）。"""
    if task.fetch_method == FetchMethod.PORTLET_POST:
        domain = _domain(task.url)
        if domain not in _PRIMED:
            prime = task.url.split("/action.uP")[0] + "/render.uP"
            async with session.get(prime, allow_redirects=True):
                pass
            _PRIMED.add(domain)
        return session.post(task.url, allow_redirects=True)
    return session.get(task.url, allow_redirects=True)


async def _fetch_one(session, task):
    url = task.url
    try:
        async with await _request(session, task) as resp:
            body = await resp.read()
            head = body[:4096].decode("utf-8", "ignore")
            if _is_cloudflare(resp.status, head):
                return FetchResult(task, FetchKind.CLOUDFLARE, resp.status)
            if resp.status == HTTPStatus.TOO_MANY_REQUESTS:   # 限流：同反爬退避重试
                return FetchResult(task, FetchKind.CLOUDFLARE, resp.status,
                                   note="HTTP 429 对方限流")
            if resp.status == HTTPStatus.NOT_FOUND:
                return FetchResult(task, FetchKind.DEAD, resp.status)
            final = str(resp.url)
            # portlet_post 的 POST→302→render.uP 是 uPortal 固有应答模式，
            # 结果在重定向后的正文里，不是页面搬家
            if (task.fetch_method != FetchMethod.PORTLET_POST
                    and resp.history and not _same_page(url, final)):
                return FetchResult(task, FetchKind.MOVED, resp.status, body, final_url=final)
            if resp.status >= HTTPStatus.INTERNAL_SERVER_ERROR:   # 5xx 多为瞬时（如 CF 520）
                return FetchResult(task, FetchKind.TRANSIENT, resp.status,
                                   note=f"HTTP {resp.status} 服务端瞬时错误")
            if resp.status != HTTPStatus.OK:
                return FetchResult(task, FetchKind.ERROR, resp.status,
                                   note=f"HTTP {resp.status}")
            return FetchResult(task, FetchKind.OK, resp.status, body, final_url=final)
    except TimeoutError:
        return FetchResult(task, FetchKind.ERROR, note=f"timeout {config.TIMEOUT}s")
    except aiohttp.ClientError as e:
        return FetchResult(task, FetchKind.ERROR, note=f"{type(e).__name__}: {e}")


async def _domain_worker(domain, queue, session, handle, sem, log):
    interval = config.domain_interval(domain)
    async with sem:
        first = True
        while queue:
            task = queue.popleft()
            if not first:
                await asyncio.sleep(interval + random.random() * config.JITTER)
            first = False

            result = await _fetch_one(session, task)
            # 5xx 瞬时错误：短暂等待重试一次
            if result.kind is FetchKind.TRANSIENT:
                await asyncio.sleep(20)
                retry = await _fetch_one(session, task)
                result = retry if retry.kind is FetchKind.OK else FetchResult(
                    task, FetchKind.ERROR, retry.http_status,
                    note=f"{result.note}（重试 1 次仍失败）")
            # Cloudflare / 429 限流：指数退避重试，用尽则失败留痕（只影响本域）
            for backoff in config.CF_BACKOFFS:
                if result.kind is not FetchKind.CLOUDFLARE:
                    break
                log(f"  [{domain}] 反爬/限流({result.note or 'CF 挑战'})，"
                    f"退避 {backoff}s: {task.url[:80]}")
                await asyncio.sleep(backoff)
                result = await _fetch_one(session, task)
            if result.kind is FetchKind.CLOUDFLARE:
                result.note = (f"{result.note or 'Cloudflare 挑战'}"
                               f" {len(config.CF_BACKOFFS)+1} 次未过，待下轮")

            handle(result)


async def _run(tasks, handle, log):
    queues: dict[str, deque] = {}
    for t in tasks:
        queues.setdefault(_domain(t.url), deque()).append(t)
    sem = asyncio.Semaphore(config.MAX_DOMAINS)
    timeout = aiohttp.ClientTimeout(total=config.TIMEOUT)
    # trust_env 默认 False：绕开本机代理环境变量（anaconda requests 曾因此出错）
    async with aiohttp.ClientSession(
            timeout=timeout, headers={"User-Agent": config.USER_AGENT}) as session:
        await asyncio.gather(*[
            _domain_worker(d, q, session, handle, sem, log)
            for d, q in queues.items()])


def fetch_tasks(tasks, handle, log=print):
    """同步入口。handle(FetchResult) 在事件循环线程内被逐个调用。"""
    if tasks:
        asyncio.run(_run(tasks, handle, log))
