"""交互式浏览器会话抓取（Playwright + CDP 合一）：应对人工 CAPTCHA 型 WAF（如 UQ）。

实测结论（2026-07，UQ AWS WAF）：
- WAF token 绑浏览器指纹 + 需人工解 CAPTCHA → 导出 cookie 给 aiohttp 无效；
- **可行做法**：全程在浏览器会话里请求——首次启动**有头** Chrome，
  用户手动过一次 CAPTCHA，之后该域所有请求走 context.request（带真 cookie+指纹）；
  一次验证撑 80+ 页（实测），会话在整轮抓取内复用，抓完关闭。

对 core 暴露 send(url) -> 一个 async 上下文管理器，进入后得到 BrowserResponse
（模仿 aiohttp 响应：status / read() / url / history），core 无需知道背后是浏览器。
页面是 SSR/内嵌 JSON（如 UQ 的 window.AppData），context.request 的原始 HTML 即够解析，
无需整页渲染，故不用 page.goto（更快）。
"""
import asyncio

import config

_LOCK = asyncio.Lock()
_STATE: dict = {}          # {'pw','browser','context','solved': set(domain)}


class BrowserResponse:
    """把 Playwright APIResponse 包成 aiohttp 响应的鸭子类型（core 只用这几样）。"""
    def __init__(self, status, body, url):
        self.status = status
        self._body = body
        self.url = url
        self.history = ()      # 浏览器会话不跟踪跳转链，空即可（不触发 MOVED）

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Fetch:
    """methods.send 返回它；async with 进入时才真正发请求（惰性，契合 core 用法）。"""
    def __init__(self, url):
        self._url = url

    async def __aenter__(self):
        return await _get(self._url)

    async def __aexit__(self, *exc):
        return False


def send(url):
    return _Fetch(url)


async def _ensure(domain):
    """惰性启动**持久化**浏览器；该域访问时先探一下——持久 profile 里的 token
    cookie 若还有效则直接开抓（无需过验证），失效才弹窗等用户手动过一次 CAPTCHA。"""
    async with _LOCK:
        if "context" not in _STATE:
            import os
            from playwright.async_api import async_playwright
            os.makedirs(config.BROWSER_PROFILE, exist_ok=True)
            pw = await async_playwright().start()
            # 持久化上下文：cookie 存 BROWSER_PROFILE，跨运行复用 → 过一次验证管几小时
            ctx = await pw.chromium.launch_persistent_context(
                config.BROWSER_PROFILE, channel="chrome", headless=False,
                viewport={"width": 1300, "height": 900})
            _STATE.update(pw=pw, context=ctx, solved=set())
        if domain in _STATE["solved"]:
            return
        old = _STATE.get("keepers", {}).pop(domain, None)   # 再挑战时先关旧守护页
        if old:
            try:
                await old.close()
            except Exception:
                pass
        page = await _STATE["context"].new_page()
        await page.goto(f"https://{domain}/", wait_until="domcontentloaded",
                        timeout=config.WAF_SOLVE_TIMEOUT * 1000)
        # 已有有效 token → 首屏就不是挑战页，直接过
        html = await page.content()
        if not any(m in html for m in config.CF_MARKERS):
            _keep(domain, page)
            return
        print(f"\n>>> 【需人工】{domain} 的验证已过期，请在弹出窗口手动过一次 CAPTCHA "
              f"（过后守护页会自动续 token，最多等 {config.WAF_SOLVE_WAIT}s）...", flush=True)
        for _ in range(config.WAF_SOLVE_WAIT // 3):
            await page.wait_for_timeout(3000)
            try:
                html = await page.content()
            except Exception:
                continue
            if not any(m in html for m in config.CF_MARKERS):
                print(f">>> ✓ {domain} 已过验证（守护页保持开着自动续 token）", flush=True)
                _keep(domain, page)
                return
        await page.close()
        raise RuntimeError(f"{domain}: {config.WAF_SOLVE_WAIT}s 内未检测到过验证（未解 CAPTCHA？）")


def _keep(domain, page):
    """把守护页留着不关：AWS WAF 的 challenge.js 在活页面上会自动续期 token
    到共享 cookie jar，ctx.request 便一直用新鲜 token，无需反复过验证。"""
    _STATE["solved"].add(domain)
    _STATE.setdefault("keepers", {})[domain] = page


async def _get(url):
    from urllib.parse import urlsplit
    domain = urlsplit(url).netloc.lower()
    await _ensure(domain)
    # 行为型 WAF（如墨尔本 Imperva）：ctx.request 带 cookie 也过不去，只有真实
    # 页面导航（page.goto 跑其 JS 挑战）才行。某域一旦吃过 403 就记入 navmode，
    # 之后该域直接走导航，不再浪费一次 ctx.request。
    if domain in _STATE.get("navmode", set()):
        return await _get_via_page(domain, url)
    r = await _STATE["context"].request.get(url, timeout=config.TIMEOUT * 1000)
    body = await r.body()
    challenged = (r.status in (403, 429, 503)
                  or any(m.encode() in body[:8192] for m in config.CF_MARKERS))
    if challenged:
        _STATE.setdefault("navmode", set()).add(domain)
        return await _get_via_page(domain, url)
    return BrowserResponse(r.status, body, url)


async def _get_via_page(domain, url):
    """真实页面导航抓取：page.goto 会执行 WAF 的 JS 挑战，几秒后自动过，
    取渲染后 HTML。用于 Imperva 等按请求行为挑战、ctx.request 过不了的域。"""
    async with _LOCK:
        page = _STATE.setdefault("navpages", {}).get(domain)
        if page is None:
            page = await _STATE["context"].new_page()
            _STATE["navpages"][domain] = page
    resp = await page.goto(url, wait_until="domcontentloaded",
                           timeout=config.TIMEOUT * 1000)
    # 挑战页会自行执行 JS 几秒后跳转真内容，轮询到不含挑战标记为止
    html = await page.content()
    for _ in range(8):
        if not any(m in html for m in config.CF_MARKERS):
            break
        await page.wait_for_timeout(2000)
        html = await page.content()
    status = resp.status if resp else 200
    still_blocked = any(m in html for m in config.CF_MARKERS)
    if still_blocked:
        # 轮询后仍是挑战/拦截页（如 Incapsula 硬封）：返回 403 让 pipeline 记失败、
        # 下轮重试，绝不把空壳当有效页入库。硬封通常需冷却才恢复。
        status = 403
    elif status >= 400:
        status = 200   # 首响应是挑战，过关后内容已是真页
    return BrowserResponse(status, html.encode("utf-8"), url)


async def close():
    """整轮抓取结束时关闭浏览器（core 在 session 收尾时调）。cookie 已随持久
    profile 存盘，下次运行复用。"""
    if "context" in _STATE:
        try:
            await _STATE["context"].close()
            await _STATE["pw"].stop()
        finally:
            _STATE.clear()   # keepers/navpages 随 context 关闭一并销毁
