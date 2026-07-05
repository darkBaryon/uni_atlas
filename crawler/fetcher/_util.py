"""fetcher 包内共享的 URL 小助手（core 与 methods 都用，独立成文件避免循环依赖）。"""
from urllib.parse import urlsplit


def domain(url):
    return urlsplit(url).netloc.lower()


def same_page(a, b):
    """301 到 https/斜杠/加 www 等价页不算搬家。"""
    def host(s):
        return s.netloc.lower().removeprefix("www.")

    def path(s):
        return (s.path.rstrip("/") or "/") + ("?" + s.query if s.query else "")

    sa, sb = urlsplit(a), urlsplit(b)
    return host(sa) == host(sb) and path(sa) == path(sb)
