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
import logging
import sys

import config
import logging_setup
import pipeline
import registry

logger = logging.getLogger(__name__)


def seed(conn, code):
    """按 config/universities/<code>.yaml 登记学校与入口页种子。"""
    uconf = config.uni(code)
    if uconf is None:
        print(f"没有 config/universities/{code}.yaml，先建配置文件。")
        return 1
    uid = registry.ensure_university(conn, uconf)
    n_new = 0
    for p in uconf.seed_pages:
        _, created = registry.add_page(
            conn, uid, p["category"], p["url"],
            crawl_freq=p.get("crawl_freq", "monthly"),
            fetch_method=p.get("fetch_method", "html"),
            note=p.get("note"))
        n_new += created
    print(f"{uconf.name} ({code}): 入口页 {len(uconf.seed_pages)} 个，新登记 {n_new} 个。"
          f"\n下一步: python3 run.py --discover --uni {code} && python3 run.py --due --uni {code}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="uni_atlas 爬虫")
    ap.add_argument("--due", action="store_true", help="仅抓 crawl_freq 已到期的任务")
    ap.add_argument("--uni", help="只跑某校 (universities.code, 如 ucl)")
    ap.add_argument("--category", help="只跑某类页面 (如 program_detail)")
    ap.add_argument("--limit", type=int, help="任务数上限")
    ap.add_argument("--discover", action="store_true", help="只跑目录类任务（展开新页面）")
    ap.add_argument("--reparse", action="store_true", help="离线重放最近快照，不联网")
    ap.add_argument("--dry-run", action="store_true", help="只列出将执行的任务")
    ap.add_argument("--verbose", action="store_true", help="控制台也输出逐页 DEBUG 日志")
    ap.add_argument("--seed", metavar="CODE",
                    help="按 config/universities/<code>.yaml 登记新学校的入口页")
    args = ap.parse_args()

    if not args.dry_run:
        logging_setup.setup(verbose=args.verbose)
    conn = registry.connect()
    if args.seed:
        return seed(conn, args.seed)
    tasks = registry.get_tasks(
        conn, uni_code=args.uni, category=args.category,
        due_only=args.due, discover_only=args.discover, limit=args.limit)

    if not tasks:
        print("没有符合条件的任务。")
        return 0
    if args.dry_run:
        print(f"将执行 {len(tasks)} 个任务:")
        for t in tasks:
            print(f"  [{t['uni_code']}/{t['category']}] {t['url']}")
        return 0

    mode = "重放" if args.reparse else "抓取"
    logger.info("%s任务 %d 个%s%s", mode, len(tasks),
                f" (uni={args.uni})" if args.uni else "",
                f" (category={args.category})" if args.category else "")

    report = pipeline.Report()
    if args.reparse:
        pipeline.run_reparse(conn, tasks, report)
    else:
        pipeline.run_fetch(conn, tasks, report)
    report.show(registry.count_skipped(conn, args.uni))
    # 页面级失败已在报告与任务表留痕，进程本身跑完即为成功（退出码 0）
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:   # 输出被 head 等截断属正常，静默退出
        sys.exit(0)
