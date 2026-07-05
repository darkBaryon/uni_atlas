#!/usr/bin/env python3
"""从 UNSW 某学院 progression-plans 索引页批量导入培养计划。

各学院同一套体系（content/dam/pdfs/<faculty>/general/course-progression/），
索引页列出全部 PDF；文件名以 4 位专业代码打头。本脚本：抓索引 →
枚举 course-progression PDF → 按代码匹配库中专业 → 导入所有完整变体
（T1 起始、非 1st-Yr、按内容去重）。

用法:  python3 crawler/import_unsw_plans.py <索引页URL>
"""
import re
import sys
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup

import plans
import registry

UA = plans.UA


def main():
    if len(sys.argv) < 2:
        print("用法: import_unsw_plans.py <学院 progression-plans 索引页 URL>")
        return 2
    idx_url = sys.argv[1]
    conn = registry.connect()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name_en FROM programs WHERE university_id="
                    "(SELECT id FROM universities WHERE code='unsw')"
                    " AND is_active=1 AND name_en REGEXP '^[0-9]{4} '")
        pbc: dict[str, int] = {}
        for r in cur.fetchall():
            pbc.setdefault(r["name_en"][:4], r["id"])

    html = requests.get(idx_url, headers={"User-Agent": UA}, timeout=60).text
    soup = BeautifulSoup(html, "html.parser")
    # 收集每个专业代码的完整计划 PDF（T1、非 1st-Yr），去重 URL
    by_code: dict[str, list] = {}
    seen = set()
    # 各学院 DAM 路径不一（course-progression / study-plans），文件名规律也不一，
    # 故不硬拼 URL：凡 dam/pdfs 下的 .pdf、文件名含库中 4 位代码、T1、非 1st-Yr 即收
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf") or "/dam/pdfs/" not in href:
            continue
        url = urljoin(idx_url, href)
        name = unquote(url.split("/")[-1])
        if "1st Yr" in name or re.search(r"1st.?year", name, re.I):
            continue
        if "T1" not in name and "term-1" not in url and "t1" not in name.lower():
            continue
        m = re.search(r"\b(\d{4})\b", name)      # 代码可能不在开头
        if not m or m.group(1) not in pbc or url in seen:
            continue
        seen.add(url)
        by_code.setdefault(m.group(1), []).append(url)

    matched = sum(len(v) for v in by_code.values())
    print(f"索引 PDF 匹配库中专业代码: {len(by_code)} 代码 / {matched} 份计划")
    ok = empty = fail = 0
    for code, urls in by_code.items():
        pid = pbc[code]
        for url in urls:
            try:
                body = requests.get(url, headers={"User-Agent": UA}, timeout=60).content
                plan = plans.parse_plan(body)
                if sum(len(y["items"]) for y in plan["years"]):
                    plans.enrich_zh(conn, pid, plan)
                    plans.load_plan(conn, pid, "2026", plan, url)
                    ok += 1
                else:
                    empty += 1
            except Exception:
                fail += 1
    print(f"导入 {ok}，空 {empty}，失败 {fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
