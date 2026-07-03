"""抓取器：域名级并行 + 域内串行限速 + Cloudflare 退避。

对外只有一个入口 fetch_tasks(tasks, handle)：
tasks 按域名分队列，每域一个 worker 串行抓取（interval + 抖动），
域间并发（上限 MAX_DOMAINS）。每个结果同步回调 handle(result)。
"""
import asyncio
import random
from urllib.parse import urlsplit

import aiohttp

import config


class FetchResult:
    """kind: ok | unchanged_hint | cloudflare | dead | moved | error"""

    def __init__(self, task, kind, http_status=None, body=b"",
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
    sa, sb = urlsplit(a), urlsplit(b)
    host = lambda s: s.netloc.lower().removeprefix("www.")
    path = lambda s: (s.path.rstrip("/") or "/") + ("?" + s.query if s.query else "")
    return host(sa) == host(sb) and path(sa) == path(sb)


def _is_cloudflare(status, text_head):
    if status in (403, 503) and any(m in text_head for m in config.CF_MARKERS):
        return True
    return any(m in text_head for m in config.CF_MARKERS)


async def _fetch_one(session, task):
    url = task["url"]
    try:
        async with session.get(url, allow_redirects=True) as resp:
            body = await resp.read()
            head = body[:4096].decode("utf-8", "ignore")
            if _is_cloudflare(resp.status, head):
                return FetchResult(task, "cloudflare", resp.status)
            if resp.status == 404:
                return FetchResult(task, "dead", 404)
            final = str(resp.url)
            if resp.history and not _same_page(url, final):
                return FetchResult(task, "moved", resp.status, body, final_url=final)
            if resp.status != 200:
                return FetchResult(task, "error", resp.status,
                                   note=f"HTTP {resp.status}")
            return FetchResult(task, "ok", 200, body, final_url=final)
    except asyncio.TimeoutError:
        return FetchResult(task, "error", note=f"timeout {config.TIMEOUT}s")
    except aiohttp.ClientError as e:
        return FetchResult(task, "error", note=f"{type(e).__name__}: {e}")


async def _domain_worker(domain, queue, session, handle, sem, log):
    interval = config.domain_interval(domain)
    async with sem:
        first = True
        while queue:
            task = queue.pop(0)
            if not first:
                await asyncio.sleep(interval + random.random() * config.JITTER)
            first = False

            result = await _fetch_one(session, task)
            # Cloudflare：指数退避重试，用尽则失败留痕（只影响本域）
            for backoff in config.CF_BACKOFFS:
                if result.kind != "cloudflare":
                    break
                log(f"  [{domain}] Cloudflare 挑战，退避 {backoff}s: {task['url'][:80]}")
                await asyncio.sleep(backoff)
                result = await _fetch_one(session, task)
            if result.kind == "cloudflare":
                result.note = f"Cloudflare 挑战 {len(config.CF_BACKOFFS)+1} 次未过，待下轮"

            handle(result)


async def _run(tasks, handle, log):
    queues = {}
    for t in tasks:
        queues.setdefault(_domain(t["url"]), []).append(t)
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
