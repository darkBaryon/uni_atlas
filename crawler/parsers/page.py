"""页面提取工具：Page 辅助类与文本解析函数（只吃本地快照，不碰网络）。"""
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup


DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%d/%m/%Y", "%Y-%m-%d")


def parse_date(s):
    """'20 Oct 2025' / '20 October 2025' 等 -> '2025-10-20'；解析不了返回 None。"""
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def money(s):
    """含 £ 金额的文本 -> float；没有返回 None。"""
    m = re.search(r"£\s*([\d,]+(?:\.\d{1,2})?)", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


class Page:
    """一张快照页的解析辅助：懒加载 soup/纯文本 + 常用提取器。"""

    def __init__(self, html, url):
        self.html = html
        self.url = url
        self._soup = None
        self._txt = None

    @property
    def soup(self):
        if self._soup is None:
            self._soup = BeautifulSoup(self.html, "html.parser")
        return self._soup

    @property
    def txt(self):
        """整页纯文本（\\n 分隔），正则字段提取都在它上面做。"""
        if self._txt is None:
            self._txt = self.soup.get_text("\n", strip=True)
        return self._txt

    def abs(self, href):
        return urljoin(self.url, href).split("#")[0]

    def h1(self):
        el = self.soup.find("h1")
        return norm_ws(el.get_text(strip=True)) if el else None

    def title_tail(self, sep=" - "):
        """<title> 的最后一段（格拉式页面的真实标题所在）。"""
        t = self.soup.title
        return t.get_text().split(sep)[-1].strip() if t else None

    def re(self, pattern, group=1, flags=0):
        """在纯文本上搜正则，返回捕获组（默认第 1 组）；无匹配返回 None。"""
        m = re.search(pattern, self.txt, flags)
        if not m:
            return None
        return m.group(group) if m.groups() else m.group(0)

    def kv(self, label, flags=0):
        """'标签:\\n值' 版式的取值：kv('Credit value') -> '15'。"""
        return self.re(label + r":?\s*\n([^\n]+)", flags=flags)

    def money(self, pattern=None, flags=0):
        """money(r'Overseas[^\\n]*\\n£([\\d,]+)')；不传 pattern 则全文找首个 £ 金额。"""
        if pattern is None:
            return money(self.txt)
        m = re.search(pattern, self.txt, flags)
        return float(m.group(1).replace(",", "")) if m else None

    def date(self, pattern, flags=0):
        """正则取到日期文本后走 parse_date。"""
        return parse_date(self.re(pattern, flags=flags))

    def links(self, css=None, href_re=None):
        """取链接 [(绝对URL, 文本)]，可按 CSS 选择器和/或 href 正则过滤，自动去重。"""
        scope = self.soup.select(css) if css else [self.soup]
        seen, out = set(), []
        for node in scope:
            for a in node.find_all("a", href=True):
                url = self.abs(a["href"])
                if href_re and not re.search(href_re, url):
                    continue
                if url in seen:
                    continue
                seen.add(url)
                out.append((url, norm_ws(a.get_text(strip=True))))
        return out

