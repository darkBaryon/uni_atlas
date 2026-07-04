"""抓取器：域名级并行 + 域内限速并发 + Cloudflare 退避。

对外只有一个入口 fetch_tasks(tasks, handle)：
tasks 按域名分队列，每域按 YAML 配置起 concurrency 个 worker 共享队列，
共享一个域级节流器（两次请求发起间隔 >= interval + 抖动，退避时全域暂停），
域间并发（上限 MAX_DOMAINS）。handle(result) 在独立消费线程里被逐个
串行调用，解析/入库不阻塞事件循环里的抓取。
"""
import asyncio
import queue
import random
import threading
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
    domain = _domain(task.url)
    if domain not in _PRIMED:
        for prime in config.domain_policy(domain).prime:   # 配置声明的会话预热链
            async with session.get(prime, allow_redirects=True):
                pass
        if task.fetch_method == FetchMethod.PORTLET_POST:  # uPortal 固定预热 render.uP
            prime = task.url.split("/action.uP")[0] + "/render.uP"
            async with session.get(prime, allow_redirects=True):
                pass
        _PRIMED.add(domain)
    if task.fetch_method == FetchMethod.PORTLET_POST:
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


class _Throttle:
    """域级节流：同域任意两次请求"发起"之间至少隔 interval + 抖动。

    并发 worker 共享一个实例排队领发车时刻；反爬退避时 pause() 把发车
    时刻整体后移，让同域所有 worker 一起停手，而不是继续往限流上撞。
    """

    def __init__(self, interval):
        self.interval = interval
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def wait(self):
        async with self._lock:
            loop = asyncio.get_running_loop()
            start = max(loop.time(), self._next_at)
            # 抖动上限跟随 interval：固定 0~1s 的抖动对高速档（0.5s）是双倍减速
            # （悉尼实测 60 页/分钟 = interval 0.5 + 平均抖动 0.5，2026-07-05）
            self._next_at = (start + self.interval
                             + random.random() * min(config.JITTER, self.interval))
            delay = start - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)

    def pause(self, seconds):
        self._next_at = max(self._next_at,
                            asyncio.get_running_loop().time() + seconds)


async def _fetch_with_retry(domain, task, session, throttle, log):
    await throttle.wait()
    result = await _fetch_one(session, task)
    # 5xx 瞬时错误：短暂等待重试一次
    if result.kind is FetchKind.TRANSIENT:
        await asyncio.sleep(20)
        await throttle.wait()
        retry = await _fetch_one(session, task)
        result = retry if retry.kind is FetchKind.OK else FetchResult(
            task, FetchKind.ERROR, retry.http_status,
            note=f"{result.note}（重试 1 次仍失败）")
    # Cloudflare / 429 限流：全域暂停指数退避，用尽则失败留痕（只影响本域）
    for backoff in config.CF_BACKOFFS:
        if result.kind is not FetchKind.CLOUDFLARE:
            break
        log(f"  [{domain}] 反爬/限流({result.note or 'CF 挑战'})，"
            f"退避 {backoff}s: {task.url[:80]}")
        throttle.pause(backoff)
        await asyncio.sleep(backoff)
        await throttle.wait()
        result = await _fetch_one(session, task)
    if result.kind is FetchKind.CLOUDFLARE:
        result.note = (f"{result.note or 'Cloudflare 挑战'}"
                       f" {len(config.CF_BACKOFFS)+1} 次未过，待下轮")
    return result


async def _domain_worker(domain, pending, session, emit, throttle, log):
    while pending:
        task = pending.popleft()
        result = await _fetch_with_retry(domain, task, session, throttle, log)
        emit(result)


async def _domain_group(domain, pending, session, emit, sem, log):
    policy = config.domain_policy(domain)
    async with sem:
        throttle = _Throttle(policy.interval)
        await asyncio.gather(*[
            _domain_worker(domain, pending, session, emit, throttle, log)
            for _ in range(max(1, min(policy.concurrency, len(pending))))])


async def _run(tasks, emit, log):
    queues: dict[str, deque] = {}
    for t in tasks:
        queues.setdefault(_domain(t.url), deque()).append(t)
    sem = asyncio.Semaphore(config.MAX_DOMAINS)
    timeout = aiohttp.ClientTimeout(total=config.TIMEOUT)
    # trust_env 默认 False：绕开本机代理环境变量（anaconda requests 曾因此出错）
    async with aiohttp.ClientSession(
            timeout=timeout, headers={"User-Agent": config.USER_AGENT}) as session:
        await asyncio.gather(*[
            _domain_group(d, q, session, emit, sem, log)
            for d, q in queues.items()])


def _consume(results, handle, log):
    while True:
        res = results.get()
        if res is None:
            return
        try:
            handle(res)
        except Exception as e:   # 消费线程不能死：单条结果异常记录后继续
            log(f"handle 异常（已跳过该页）: {res.task.url[:80]}  "
                f"{type(e).__name__}: {e}")


def fetch_tasks(tasks, handle, log=print):
    """同步入口。抓取协程只投递结果；handle(FetchResult) 在独立消费线程
    里被逐个串行调用（顺序语义与旧版一致，数据库连接只在该线程使用）。"""
    if not tasks:
        return
    results: queue.Queue = queue.Queue()
    consumer = threading.Thread(target=_consume, args=(results, handle, log),
                                name="fetch-handle")
    consumer.start()
    try:
        asyncio.run(_run(tasks, results.put, log))
    finally:
        results.put(None)
        consumer.join()
