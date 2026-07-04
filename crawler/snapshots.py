"""快照层：原始 HTML 落盘 + sha256 变更检测 + page_snapshots 登记。

解析器只吃这里落盘的文件，从不直接吃网络响应（可离线重放）。
"""
import gzip
import hashlib
import os
import re
from datetime import datetime

import config


def _slug(url):
    """URL → 快照文件名：取路径全段而非仅尾段——不同页面共享尾段
    （/schools/A/study/postgraduate 与 /schools/B/study/postgraduate）
    曾互相覆盖（实测 2026-07）。"""
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    path = parts.path.strip("/") or "index"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", path.replace("/", "__"))
    if parts.query:
        slug += "_" + re.sub(r"[^A-Za-z0-9]+", "-", parts.query)[:60]
    return slug[-160:]


def path_for(uni_code, category, url):
    # gzip 落盘：HTML 压缩比 ~6:1（12,530 页 1.5G → ~250M，实测 2026-07）
    return os.path.join(config.SNAP_ROOT, uni_code, category, _slug(url) + ".html.gz")


def save(conn, task, body_bytes, http_status):
    """落盘 + 登记。返回 (content_hash, changed, snapshot_id)。

    哈希与库中 last_content_hash 一致 → 未变更：不写盘不登记，返回 snapshot_id=None。
    """
    content_hash = hashlib.sha256(body_bytes).hexdigest()
    # 以库中最近快照为准判断"未变"——任务行的 last_content_hash 是取任务时的
    # 旧值，双进程并跑/中途崩溃会让它落后，曾造成 461 组重复快照
    with conn.cursor() as cur:
        cur.execute("SELECT content_hash FROM page_snapshots WHERE source_page_id=%s"
                    " ORDER BY id DESC LIMIT 1", (task.id,))
        row = cur.fetchone()
    prev_hash = row["content_hash"] if row else task.last_content_hash
    if content_hash == prev_hash:
        return content_hash, False, None

    fpath = path_for(task.uni_code, task.category, task.url)
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    with gzip.open(fpath, "wb", compresslevel=6) as f:
        f.write(body_bytes)

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO page_snapshots (source_page_id, fetched_at, http_status,"
            " content_hash, content_path) VALUES (%s,%s,%s,%s,%s)",
            (task.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             http_status, content_hash, fpath))
        return content_hash, True, cur.lastrowid


def latest_snapshot(conn, source_page_id):
    """--reparse 用：取该页面最近一次快照（含磁盘路径）。"""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM page_snapshots WHERE source_page_id=%s"
                    " ORDER BY fetched_at DESC, id DESC LIMIT 1", (source_page_id,))
        return cur.fetchone()


def mark_parsed(conn, snapshot_id, ok=True):
    if snapshot_id is None:
        return
    with conn.cursor() as cur:
        cur.execute("UPDATE page_snapshots SET parsed_ok=%s WHERE id=%s",
                    (1 if ok else 0, snapshot_id))


def read(content_path):
    opener = gzip.open if content_path.endswith(".gz") else open   # 兼容未压缩旧快照
    with opener(content_path, "rb") as f:
        return f.read()
