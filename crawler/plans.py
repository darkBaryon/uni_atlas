#!/usr/bin/env python3
"""培养计划 PDF 解析 + 入库（新南试点，2026-07-06）。

新南工程学院的 progression checksheet 是 PDF（文本层干净、非扫描）：
按「专业代码 × 主修 × 起始学期」一份，内含逐年逐 term 的修课序列
+ 先修关系。用 pdfplumber 的**词坐标分列**（表头 Prerequisites/Credits
的 x 边界切三列）而非正则合并文本——后者对 "A or B" 二选一会误拆先修。

产出存 program_plans（新表，见 db/schema.sql）：一行一份计划，
plan 列是结构化 JSON（years[].items[]）。前端专业页渲染修课路线图。

用法:  python3 crawler/plans.py --uni unsw --url <PDF> --program-id N
       （试点手动指定；铺开时改为从 checksheet 目录页枚举）
"""
import argparse
import io
import json
import logging
import re
import sys

import requests

import logging_setup
import registry

logger = logging.getLogger(__name__)

CODE = re.compile(r"[A-Z]{2,4}\d{4}")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
      " (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def parse_plan(pdf_bytes):
    """PDF bytes → {'years': [{year, term, items:[{code?,label,prereq?,credits}]}]}。"""
    import pdfplumber
    years = []
    cur = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            # 每页表头定列边界（个别页 Prerequisites 左移到 408，取本页实测值）
            xs = [w["x0"] for w in words if w["text"] == "Prerequisites"]
            x_pre = min(xs) - 8 if xs else 400
            xc = [w["x0"] for w in words if w["text"] == "Credits"]
            x_cr = min(xc) - 8 if xc else 510
            # 按 y(top) 聚成行
            rows: dict[int, list] = {}
            for w in words:
                rows.setdefault(round(w["top"]), []).append(w)
            for top in sorted(rows):
                ws = sorted(rows[top], key=lambda w: w["x0"])
                line = " ".join(w["text"] for w in ws).strip()
                ym = re.match(r"Year (\d+) Term (\d+)", line)
                if ym:
                    cur = {"year": int(ym.group(1)), "term": int(ym.group(2)), "items": []}
                    years.append(cur)
                    continue
                if cur is None or line.startswith("Course or Activity") or not line:
                    continue
                name = " ".join(w["text"] for w in ws if w["x0"] < x_pre).strip()
                prereq = " ".join(w["text"] for w in ws if x_pre <= w["x0"] < x_cr).strip()
                credit = " ".join(w["text"] for w in ws if w["x0"] >= x_cr).strip()
                if not name or not credit.isdigit():
                    continue
                lead = CODE.match(name)
                item = {"credits": int(credit)}
                if lead and "or" not in name.split(lead.group(0), 1)[1][:4].lower():
                    item["code"] = lead.group(0)
                    item["label"] = name[lead.end():].strip() or lead.group(0)
                else:
                    item["label"] = name          # 'A or B' 二选一 / 纯活动名整体留 label
                if prereq:
                    item["prereq"] = prereq
                cur["items"].append(item)
    return {"years": years}


def variant_label(url):
    """从 PDF 文件名提取变体标签（去代码/年级前缀，保主修+起始学期）。"""
    from urllib.parse import unquote
    name = unquote(url.split("/")[-1]).rsplit(".pdf", 1)[0]
    name = re.sub(r"^\d{4}\s*-\s*", "", name)
    name = re.sub(r"\b1st Yr\b\s*-?\s*", "", name)
    return re.sub(r"\s+", " ", name).strip()


def load_plan(conn, program_id, entry_year, plan, url):
    label = variant_label(url)
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM program_plans WHERE program_id=%s"
                    " AND variant_label=%s AND entry_year=%s",
                    (program_id, label, entry_year))
        row = cur.fetchone()
        payload = json.dumps(plan, ensure_ascii=False)
        if row:
            cur.execute("UPDATE program_plans SET plan=%s, source_url=%s WHERE id=%s",
                        (payload, url, row["id"]))
        else:
            cur.execute("INSERT INTO program_plans (program_id, variant_label,"
                        " entry_year, plan, source_url) VALUES (%s,%s,%s,%s,%s)",
                        (program_id, label, entry_year, payload, url))
    conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="培养计划 PDF 直链")
    ap.add_argument("--program-id", type=int, required=True)
    ap.add_argument("--entry-year", default="2026")
    args = ap.parse_args()
    logging_setup.setup()
    body = requests.get(args.url, headers={"User-Agent": UA}, timeout=60).content
    plan = parse_plan(body)
    n = sum(len(y["items"]) for y in plan["years"])
    if not n:
        logger.error("解析出 0 条目，PDF 版式可能不同，未入库")
        return 1
    conn = registry.connect()
    load_plan(conn, args.program_id, args.entry_year, plan, args.url)
    logger.info("培养计划入库：program %d，%d 学期 %d 条目",
                args.program_id, len(plan["years"]), n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
