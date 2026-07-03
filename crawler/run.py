#!/usr/bin/env python3
"""uni_atlas 爬虫 CLI。

  python3 run.py --due                    # 抓所有到期任务（日常 cron 用）
  python3 run.py --uni ucl                # 只跑某校（全部 active 任务）
  python3 run.py --uni ucl --category program_detail --limit 50
  python3 run.py --discover --uni ucl     # 只跑发现任务（展开目录）
  python3 run.py --reparse --uni ucl      # 离线重放快照（不联网）
  python3 run.py --dry-run                # 只列出将执行的任务
"""
import argparse
import sys

import pipeline
import registry


def main():
    ap = argparse.ArgumentParser(description="uni_atlas 爬虫")
    ap.add_argument("--due", action="store_true", help="仅抓 crawl_freq 已到期的任务")
    ap.add_argument("--uni", help="只跑某校 (universities.code, 如 ucl)")
    ap.add_argument("--category", help="只跑某类页面 (如 program_detail)")
    ap.add_argument("--limit", type=int, help="任务数上限")
    ap.add_argument("--discover", action="store_true", help="只跑目录类任务（展开新页面）")
    ap.add_argument("--reparse", action="store_true", help="离线重放最近快照，不联网")
    ap.add_argument("--dry-run", action="store_true", help="只列出将执行的任务")
    args = ap.parse_args()

    conn = registry.connect()
    tasks = registry.get_tasks(
        conn, uni_code=args.uni, category=args.category,
        due_only=args.due, discover_only=args.discover, limit=args.limit)

    if not tasks:
        print("没有符合条件的任务。")
        return 0
    mode = "重放" if args.reparse else "抓取"
    print(f"{mode}任务 {len(tasks)} 个"
          + (f" (uni={args.uni})" if args.uni else "")
          + (f" (category={args.category})" if args.category else ""))

    if args.dry_run:
        for t in tasks:
            print(f"  [{t['uni_code']}/{t['category']}] {t['url']}")
        return 0

    report = pipeline.Report()
    if args.reparse:
        pipeline.run_reparse(conn, tasks, report)
    else:
        pipeline.run_fetch(conn, tasks, report)
    report.show(registry.count_skipped(conn, args.uni))
    return 1 if report.counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
