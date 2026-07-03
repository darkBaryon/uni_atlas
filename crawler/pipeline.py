"""流水线编排：取任务 → 抓取 → 快照 → 解析 → 装载 → 报告。

- 单页解析/入库异常只记日志（含堆栈）并计入失败，绝不中断整轮运行；
- TTY 下显示 rich 进度条；后台/重定向时退化为每 50 页一行进度日志；
- reparse 模式跳过抓取，直接离线重放磁盘上最近一次快照。
"""
import logging
from collections import Counter

import discover
import fetcher
import progress
import registry
import snapshots
from loader import Loader
from parsers.base import get_parser

logger = logging.getLogger(__name__)

FAILURE_MARKERS = ("失败", "Cloudflare", "待重试", "待下轮", "timeout", "异常")
PROGRESS_EVERY = 50   # 非 TTY 时每 N 页写一行进度日志


class Report:
    def __init__(self):
        self.counts = Counter()
        self.no_parser = Counter()
        self.failures = []      # (url, note)
        self.new_tasks = 0
        self.loader_stats = Counter()
        self.changes = []

    def show(self, skipped):
        logger.info("========== 运行报告 ==========")
        for k, label in (("fetched", "抓取"), ("unchanged", "内容未变(跳过解析)"),
                         ("changed", "有变更并解析"), ("reparsed", "离线重放"),
                         ("moved", "已搬家(301)"), ("dead", "已失效(404)"),
                         ("failed", "失败")):
            if self.counts[k]:
                logger.info("  %s: %d", label, self.counts[k])
        if self.new_tasks:
            logger.info("  新发现任务: %d", self.new_tasks)
        for k, label in (("programs", "专业"), ("modules", "模块"),
                         ("deadlines", "截止日期"), ("calendar", "校历事件")):
            if self.loader_stats[k]:
                logger.info("  入库 %s: %d", label, self.loader_stats[k])
        if self.no_parser:
            logger.info("  无解析器跳过: %s",
                        ", ".join(f"{c}×{n}" for c, n in self.no_parser.items()))
        if skipped:
            logger.info("  v1 不抓(js_render/pdf): %s",
                        ", ".join(f"{m}×{n}" for m, n in skipped.items()))
        if self.failures:
            logger.warning("  失败明细 (%d):", len(self.failures))
            for url, note in self.failures[:10]:
                logger.warning("    - %s  (%s)", url[:90], note)
        if self.changes:
            logger.info("  变更摘要 (change_log):")
            for ent, label, field, old, new in self.changes[:20]:
                logger.info("    - [%s] %s: %s %s -> %s", ent, label, field, old, new)
        logger.info("==============================")


def _clean_note(old_note):
    """成功后清掉错误类 note，保留 discovery 写入的院系信息。"""
    if old_note and any(m in old_note for m in FAILURE_MARKERS):
        return None
    return old_note


def _parse_and_load(conn, ldr, task, body, snapshot_id, report):
    parser = get_parser(task["uni_code"], task["category"])
    if parser is None:
        report.no_parser[task["category"]] += 1
        return
    result = parser(body, task["url"])
    uid = task["university_id"]

    for p in result.programs:
        ldr.load_program(p, task["id"], snapshot_id, faculty_note=task.get("note"))
    for m in result.modules:
        ldr.load_module(m, task["id"], snapshot_id)
    for c in result.calendar:
        ldr.load_calendar(c, task["id"], snapshot_id)
    for d in result.deadlines:
        ldr.load_deadline(d, task["id"], snapshot_id)

    report.new_tasks += discover.register_discovered(conn, uid, result.discovered)
    report.new_tasks += discover.register_module_pages(conn, uid, result.programs)
    snapshots.mark_parsed(conn, snapshot_id, ok=True)
    if result.counts():
        logger.debug("    -> %s", result.counts())
    for note in result.notes:
        logger.warning("    !! %s (%s)", note, task["url"][:80])


def _handle_fetched(conn, ldr, task, res, report):
    short = task["url"][:80]
    if res.kind == "dead":
        registry.mark_dead(conn, task["id"], "404")
        report.counts["dead"] += 1
        logger.warning("[404] %s", short)
    elif res.kind == "moved":
        registry.mark_moved(conn, task["id"], res.final_url)
        _, created = registry.add_page(
            conn, task["university_id"], task["category"], res.final_url,
            title=task.get("title"), crawl_freq=task["crawl_freq"],
            note=task.get("note"))
        report.new_tasks += created
        report.counts["moved"] += 1
        logger.info("[301] %s -> %s", short, res.final_url[:60])
    elif res.kind in ("error", "cloudflare"):
        registry.mark_failed(conn, task["id"], res.note)
        report.counts["failed"] += 1
        report.failures.append((task["url"], res.note))
        logger.warning("[失败] %s  (%s)", short, res.note)
    else:  # ok
        report.counts["fetched"] += 1
        content_hash, changed, snap_id = snapshots.save(
            conn, task, res.body, res.http_status)
        if not changed:
            registry.mark_fetched(conn, task["id"], content_hash,
                                  changed=False, note=_clean_note(task.get("note")))
            report.counts["unchanged"] += 1
            logger.debug("[未变] %s", short)
            return
        logger.debug("[变更] %s", short)
        _parse_and_load(conn, ldr, task, res.body, snap_id, report)
        registry.mark_fetched(conn, task["id"], content_hash,
                              changed=True, note=_clean_note(task.get("note")))
        report.counts["changed"] += 1


def run_fetch(conn, tasks, report):
    ldr_by_uni = {}
    state = {"done": 0}
    total = len(tasks)

    with progress.stage_bar("抓取", total) as bar:
        def handle(res):
            task = res.task
            state["done"] += 1
            bar.describe(f"[{task['category']}] {task['url'][:60]}")
            bar.advance()
            if state["done"] % PROGRESS_EVERY == 0:
                logger.info("进度 %d/%d（失败 %d，变更 %d）", state["done"], total,
                            report.counts["failed"], report.counts["changed"])
            try:
                conn.ping(reconnect=True)   # 长任务期间数据库连接掉线自愈
                ldr = ldr_by_uni.setdefault(
                    task["university_id"], Loader(conn, task["university_id"]))
                _handle_fetched(conn, ldr, task, res, report)
            except Exception:
                # 单页失败绝不中断整轮：堆栈进文件日志，任务表留痕待下轮
                logger.exception("[异常] 处理失败（继续运行）: %s", task["url"])
                report.counts["failed"] += 1
                report.failures.append((task["url"], "处理异常，详见日志"))
                try:
                    registry.mark_failed(conn, task["id"], "处理异常，待下轮重试")
                except Exception:
                    logger.exception("任务表留痕也失败: %s", task["url"])

        fetcher.fetch_tasks(tasks, handle, log=logger.warning)
    _collect(ldr_by_uni, report)


def run_reparse(conn, tasks, report):
    ldr_by_uni = {}
    with progress.stage_bar("重放", len(tasks)) as bar:
        for task in tasks:
            bar.describe(f"[{task['category']}] {task['url'][:60]}")
            bar.advance()
            snap = snapshots.latest_snapshot(conn, task["id"])
            if not snap or not snap.get("content_path"):
                continue
            try:
                body = snapshots.read(snap["content_path"])
                ldr = ldr_by_uni.setdefault(
                    task["university_id"], Loader(conn, task["university_id"]))
                logger.debug("[重放] %s", task["url"][:80])
                _parse_and_load(conn, ldr, task, body, snap["id"], report)
                report.counts["reparsed"] += 1
            except Exception:
                logger.exception("[异常] 重放失败（继续运行）: %s", task["url"])
                report.counts["failed"] += 1
                report.failures.append((task["url"], "重放异常，详见日志"))
    _collect(ldr_by_uni, report)


def _collect(ldr_by_uni, report):
    for ldr in ldr_by_uni.values():
        report.loader_stats.update(ldr.stats)
        report.changes.extend(ldr.changes)
