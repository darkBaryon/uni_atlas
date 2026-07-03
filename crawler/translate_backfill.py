#!/usr/bin/env python3
"""把库里还没有中文名的 学校/院系/专业/课程 批量翻译回填。

用法:  python3 crawler/translate_backfill.py [--limit N]
幂等增量：只翻 name_zh IS NULL 的行，跑过的不再动；
同名行共享译文（先查库里已有的同名翻译再调模型）。
run.sh update 在爬取后自动调用本脚本。
"""
import argparse
import logging
import sys

import registry
import logging_setup
from translate import to_zh

logger = logging.getLogger(__name__)

# (表, 主键, 英文列, 中文列, 附加条件)
TARGETS = [
    ("universities", "id", "name_en", "name_zh", ""),
    ("faculties",    "id", "name_en", "name_zh", ""),
    ("programs",     "id", "name_en", "name_zh", "AND is_active=1"),
    ("modules",      "id", "name_en", "name_zh", "AND is_active=1"),
]


def backfill(conn, limit=None):
    total = 0
    for table, pk, en, zh, cond in TARGETS:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {pk} AS id, {en} AS en FROM {table}"
                        f" WHERE {zh} IS NULL AND {en} IS NOT NULL {cond}")
            rows = cur.fetchall()
        if limit:
            rows = rows[: max(0, limit - total)]
        if not rows:
            continue
        # 库内已有的同名译文直接复用
        with conn.cursor() as cur:
            cur.execute(f"SELECT {en} AS en, {zh} AS zh FROM {table}"
                        f" WHERE {zh} IS NOT NULL GROUP BY {en}, {zh}")
            known = {r["en"]: r["zh"] for r in cur.fetchall()}

        n = 0
        for i, r in enumerate(rows, 1):
            zh_val = known.get(r["en"]) or to_zh(r["en"])
            if not zh_val:
                continue
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {table} SET {zh}=%s WHERE {pk}=%s",
                            (zh_val, r["id"]))
            n += 1
            if i % 200 == 0:
                logger.info("  %s: %d/%d", table, i, len(rows))
        logger.info("%s: 回填 %d/%d 条", table, n, len(rows))
        total += n
        if limit and total >= limit:
            break
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="最多翻译 N 条（试跑用）")
    args = ap.parse_args()
    logging_setup.setup()
    conn = registry.connect()
    n = backfill(conn, args.limit)
    logger.info("翻译回填完成：共 %d 条", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
