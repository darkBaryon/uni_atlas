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
    """惰性启动浏览器 + 该域首次访问时等用户手动过 CAPTCHA（每域一次）。"""
    async with _LOCK:
        if "browser" not in _STATE:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=False, channel="chrome")
            _STATE.update(pw=pw, browser=browser,
                          context=await browser.new_context(
                              viewport={"width": 1300, "height": 900}),
                          solved=set())
        if domain in _STATE["solved"]:
            return
        page = await _STATE["context"].new_page()
        await page.goto(f"https://{domain}/", wait_until="domcontentloaded",
                        timeout=config.WAF_SOLVE_TIMEOUT * 1000)
        print(f"\n>>> 【需人工】浏览器已弹出 {domain}，请在窗口里手动过 CAPTCHA "
              f"（最多等 {config.WAF_SOLVE_WAIT}s）...", flush=True)
        for _ in range(config.WAF_SOLVE_WAIT // 3):
            await page.wait_for_timeout(3000)
            try:
                html = await page.content()
            except Exception:
                continue
            if not any(m in html for m in config.CF_MARKERS):
                print(f">>> ✓ {domain} 已过验证，开始抓取", flush=True)
                _STATE["solved"].add(domain)
                await page.close()
                return
        await page.close()
        raise RuntimeError(f"{domain}: {config.WAF_SOLVE_WAIT}s 内未检测到过验证（未解 CAPTCHA？）")


async def _get(url):
    from urllib.parse import urlsplit
    domain = urlsplit(url).netloc.lower()
    await _ensure(domain)
    r = await _STATE["context"].request.get(url, timeout=config.TIMEOUT * 1000)
    body = await r.body()
    # 会话过期 / WAF 再挑战：作废该域标记，重新等用户过一次，然后重取
    if any(m.encode() in body[:8192] for m in config.CF_MARKERS):
        _STATE["solved"].discard(domain)
        await _ensure(domain)
        r = await _STATE["context"].request.get(url, timeout=config.TIMEOUT * 1000)
        body = await r.body()
    return BrowserResponse(r.status, body, url)


async def close():
    """整轮抓取结束时关闭浏览器（core 在 session 收尾时调）。"""
    if "browser" in _STATE:
        try:
            await _STATE["browser"].close()
            await _STATE["pw"].stop()
        finally:
            _STATE.clear()
