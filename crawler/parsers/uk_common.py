"""Small helpers shared by UK university parsers.

Keep this file boring: selectors and school-specific rules stay in each parser.
"""
import re
from urllib.parse import parse_qs, unquote, urlparse, urlsplit, urlunsplit

from parsers.base import norm_ws, money, parse_date


def clean_url(url, keep_query=False):
    parts = urlsplit(url)
    path = parts.path.rstrip("/") + ("/" if parts.path.rstrip("/") else "")
    query = parts.query if keep_query else ""
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def title_from(page, bad_h1=(), suffix_re=None):
    candidates = []
    h1_el = page.soup.find("h1")
    h1 = norm_ws(h1_el.get_text(" ", strip=True)) if h1_el else None
    if h1 and h1.lower() not in {x.lower() for x in bad_h1}:
        candidates.append(h1)
    meta = page.soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        candidates.append(meta["content"])
    if page.soup.title:
        candidates.append(page.soup.title.get_text(" ", strip=True))
    for text in candidates:
        if suffix_re:
            text = re.sub(suffix_re, "", text, flags=re.I)
        text = norm_ws(text)
        if text:
            return text
    return None


def find_links(page, href_re):
    seen = set()
    for a in page.soup.find_all("a", href=True):
        url = page.abs(a["href"])
        if not re.search(href_re, url, re.I):
            continue
        url = clean_url(url)
        if url in seen:
            continue
        seen.add(url)
        yield url, norm_ws(a.get_text(" ", strip=True)), a


def facts(page):
    out = {}
    for dl in page.soup.find_all("dl"):
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            key = norm_ws(dt.get_text(" ", strip=True)).rstrip(":").lower()
            val = norm_ws(dd.get_text(" ", strip=True))
            if key and val and key not in out:
                out[key] = val
    return out


def pick(mapping, *labels):
    for label in labels:
        key = label.lower()
        if key in mapping:
            return mapping[key]
    for key, val in mapping.items():
        if any(label.lower() in key for label in labels):
            return val
    return None


def first(txt, *patterns, flags=re.I):
    for pattern in patterns:
        m = re.search(pattern, txt or "", flags)
        if m:
            return norm_ws(m.group(1) if m.groups() else m.group(0))
    return None


def fee_near(txt, labels):
    for label in labels:
        for hit in re.finditer(re.escape(label), txt or "", re.I):
            tail = (txt or "")[hit.end():hit.end() + 500]
            if "deposit" in tail[:120].lower() or "application fee" in tail[:120].lower():
                continue
            val = money(tail)
            if val is not None:
                return val
    lines = (txt or "").splitlines()
    for i, line in enumerate(lines):
        if "£" not in line:
            continue
        ctx = " ".join(lines[max(0, i - 4):i + 2]).lower()
        if any(label.lower() in ctx for label in labels) and "deposit" not in ctx:
            val = money(line)
            if val is not None:
                return val
    for label in labels:
        m = re.search(re.escape(label) + r"[^£]{0,220}(£\s*[\d,]+(?:\.\d{1,2})?)",
                      txt or "", re.I | re.S)
        if m:
            return money(m.group(1))
    return None


def ielts(txt):
    """IELTS 提及附近取 (总分, 单项最低)。

    只认雅思有效分数区间 4.0–9.0，且优先带小数点形式（'6.5'），
    避免 '4 years'、'2 semesters' 之类的整数污染最低分。
    """
    nums = []
    for m in re.finditer(r"IELTS.{0,260}", txt or "", re.I | re.S):
        seg = m.group(0)
        vals = [float(x) for x in re.findall(r"\b([4-9]\.[05])\b", seg)]
        if not vals:  # 个别学校写整分（'IELTS 7'）：仅在无小数形式时退化接受
            vals = [float(x) for x in re.findall(r"\bIELTS\D{0,30}\b([4-9])\b", seg)]
        nums.extend(v for v in vals if 4.0 <= v <= 9.0)
    if not nums:
        return None, None
    return max(nums), min(nums) if len(set(nums)) > 1 else None


def section_text(page, heading_re, stop_re=None, limit=800):
    heading = page.soup.find(re.compile(r"h[1-6]"), string=re.compile(heading_re, re.I))
    if heading:
        parts = []
        for node in heading.find_all_next(["h2", "h3", "h4", "p", "li", "td"]):
            if node is heading:
                continue
            if node.name in ("h2", "h3", "h4"):
                if stop_re is None or parts or re.search(stop_re, node.get_text(" ", strip=True), re.I):
                    break
            if node.name in ("p", "li", "td"):
                text = norm_ws(node.get_text(" ", strip=True))
                if text:
                    parts.append(text)
            if len(" ".join(parts)) > limit:
                break
        if parts:
            return " ".join(parts)[:limit]
    if stop_re:
        m = re.search(heading_re + r"\s*\n(.{20," + str(limit) + r"}?)(?=\n" + stop_re + r"|\Z)",
                      page.txt, re.I | re.S)
    else:
        m = re.search(heading_re + r"\s*\n(.{20," + str(limit) + r"}?)(?:\n[A-Z][^\n]{2,80}\n|\Z)",
                      page.txt, re.I | re.S)
    return norm_ws(m.group(1))[:limit] if m else None


def date_loose(text):
    text = norm_ws(text or "")
    text = re.sub(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+", "",
                  text, flags=re.I)
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.I)
    return parse_date(text)


def date_range(text):
    clean = norm_ws((text or "").replace("\u2013", "-").replace("\u2014", "-"))
    clean = re.sub(r"\([^)]*\)", "", clean)
    m = re.search(r"(\d{1,2})(?:\s+([A-Za-z]+))?(?:\s+(20\d{2}))?\s*(?:-|to)\s*"
                  r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", clean, re.I)
    if m:
        start_month = m.group(2) or m.group(5)
        start_year = m.group(3) or m.group(6)
        return (date_loose(f"{m.group(1)} {start_month} {start_year}"),
                date_loose(f"{m.group(4)} {m.group(5)} {m.group(6)}"))
    dates = re.findall(r"\b\d{1,2}\s+[A-Za-z]+\s+20\d{2}\b", clean)
    if len(dates) >= 2:
        return date_loose(dates[0]), date_loose(dates[1])
    if len(dates) == 1:
        d = date_loose(dates[0])
        return d, d
    return None, None


def event_type(name, start=None):
    n = (name or "").lower()
    if "welcome" in n or "induction" in n:
        return "welcome_week"
    if "exam" in n or "assessment" in n or "revision" in n:
        return "resit_period" if start and start[5:7] in ("07", "08") else "exam_period"
    if "resit" in n:
        return "resit_period"
    if "vacation" in n or "closure" in n or "holiday" in n or "break" in n:
        return "closure"
    if "graduation" in n:
        return "graduation"
    if "term" in n or "semester" in n or "teaching" in n:
        return "teaching_period"
    return "other"


def known_name(names, text):
    if not names or not text:
        return None
    hay = norm_ws(text).lower().replace(" and ", " & ")
    for name in names:
        needle = norm_ws(name).lower().replace(" and ", " & ")
        if needle in hay:
            return name
    return None


def unwrap_funnelback(url):
    parsed = urlparse(url)
    if "funnelback" not in parsed.netloc:
        return url.split("#")[0]
    target = parse_qs(parsed.query).get("url", [None])[0]
    return unquote(target).split("#")[0] if target else ""
