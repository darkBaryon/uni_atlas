"""流水线编排：取任务 → 抓取 → 快照 → 解析 → 装载 → 报告。

reparse 模式跳过抓取，直接离线重放磁盘上最近一次快照。
"""
from collections import Counter

import discover
import fetcher
import registry
import snapshots
from loader import Loader
from parsers.base import get_parser

FAILURE_MARKERS = ("失败", "Cloudflare", "待重试", "待下轮", "timeout")


class Report:
    def __init__(self):
        self.counts = Counter()
        self.no_parser = Counter()
        self.failures = []      # (url, note)
        self.new_tasks = 0
        self.loader_stats = Counter()
        self.changes = []

    def show(self, skipped):
        print("\n========== 运行报告 ==========")
        for k, label in (("fetched", "抓取"), ("unchanged", "内容未变(跳过解析)"),
                         ("changed", "有变更并解析"), ("reparsed", "离线重放"),
                         ("moved", "已搬家(301)"), ("dead", "已失效(404)"),
                         ("failed", "失败")):
            if self.counts[k]:
                print(f"  {label}: {self.counts[k]}")
        if self.new_tasks:
            print(f"  新发现任务: {self.new_tasks}")
        for k, label in (("programs", "专业"), ("modules", "模块"),
                         ("deadlines", "截止日期"), ("calendar", "校历事件")):
            if self.loader_stats[k]:
                print(f"  入库 {label}: {self.loader_stats[k]}")
        if self.no_parser:
            pairs = ", ".join(f"{c}×{n}" for c, n in self.no_parser.items())
            print(f"  无解析器跳过: {pairs}")
        if skipped:
            pairs = ", ".join(f"{m}×{n}" for m, n in skipped.items())
            print(f"  v1 不抓(js_render/pdf): {pairs}")
        if self.failures:
            print("  失败明细:")
            for url, note in self.failures[:10]:
                print(f"    - {url[:90]}  ({note})")
        if self.changes:
            print("  变更摘要 (change_log):")
            for ent, label, field, old, new in self.changes[:20]:
                print(f"    - [{ent}] {label}: {field} {old} -> {new}")
        print("==============================")


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
        print(f"    -> {result.counts()}")
    for note in result.notes:
        print(f"    !! {note}")


def run_fetch(conn, tasks, report, log=print):
    ldr_by_uni = {}

    def handle(res):
        task = res.task
        ldr = ldr_by_uni.setdefault(
            task["university_id"], Loader(conn, task["university_id"]))
        short = task["url"][:80]
        if res.kind == "dead":
            registry.mark_dead(conn, task["id"], "404")
            report.counts["dead"] += 1
            log(f"  [404] {short}")
        elif res.kind == "moved":
            registry.mark_moved(conn, task["id"], res.final_url)
            _, created = registry.add_page(
                conn, task["university_id"], task["category"], res.final_url,
                title=task.get("title"), crawl_freq=task["crawl_freq"],
                note=task.get("note"))
            report.new_tasks += created
            report.counts["moved"] += 1
            log(f"  [301] {short} -> {res.final_url[:60]}")
        elif res.kind in ("error", "cloudflare"):
            registry.mark_failed(conn, task["id"], res.note)
            report.counts["failed"] += 1
            report.failures.append((task["url"], res.note))
            log(f"  [失败] {short}  ({res.note})")
        else:  # ok
            report.counts["fetched"] += 1
            content_hash, changed, snap_id = snapshots.save(
                conn, task, res.body, res.http_status)
            if not changed:
                registry.mark_fetched(conn, task["id"], content_hash,
                                      changed=False, note=_clean_note(task.get("note")))
                report.counts["unchanged"] += 1
                log(f"  [未变] {short}")
                return
            log(f"  [变更] {short}")
            _parse_and_load(conn, ldr, task, res.body, snap_id, report)
            registry.mark_fetched(conn, task["id"], content_hash,
                                  changed=True, note=_clean_note(task.get("note")))
            report.counts["changed"] += 1

    fetcher.fetch_tasks(tasks, handle, log=log)
    _collect(ldr_by_uni, report)


def run_reparse(conn, tasks, report, log=print):
    ldr_by_uni = {}
    for task in tasks:
        snap = snapshots.latest_snapshot(conn, task["id"])
        if not snap or not snap.get("content_path"):
            continue
        try:
            body = snapshots.read(snap["content_path"])
        except OSError as e:
            report.failures.append((task["url"], f"快照文件不可读: {e}"))
            continue
        ldr = ldr_by_uni.setdefault(
            task["university_id"], Loader(conn, task["university_id"]))
        log(f"  [重放] {task['url'][:80]}")
        _parse_and_load(conn, ldr, task, body, snap["id"], report)
        report.counts["reparsed"] += 1
    _collect(ldr_by_uni, report)


def _collect(ldr_by_uni, report):
    for ldr in ldr_by_uni.values():
        report.loader_stats.update(ldr.stats)
        report.changes.extend(ldr.changes)
