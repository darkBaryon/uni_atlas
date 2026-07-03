"""快照层：原始 HTML 落盘 + sha256 变更检测 + page_snapshots 登记。

解析器只吃这里落盘的文件，从不直接吃网络响应（可离线重放）。
"""
import hashlib
import os
import re
from datetime import datetime

import config


def _slug(url):
    tail = url.rstrip("/").split("/")[-1] or "index"
    tail = tail.split("?")[0] or "index"
    query = url.split("?", 1)[1] if "?" in url else ""
    if query:  # 目录分页等带参页面，参数并入文件名避免互相覆盖
        tail += "_" + re.sub(r"[^A-Za-z0-9]+", "-", query)[:60]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", tail)[:120]


def path_for(uni_code, category, url):
    return os.path.join(config.SNAP_ROOT, uni_code, category, _slug(url) + ".html")


def save(conn, task, body_bytes, http_status):
    """落盘 + 登记。返回 (content_hash, changed, snapshot_id)。

    哈希与库中 last_content_hash 一致 → 未变更：不写盘不登记，返回 snapshot_id=None。
    """
    content_hash = hashlib.sha256(body_bytes).hexdigest()
    if content_hash == task.last_content_hash:
        return content_hash, False, None

    fpath = path_for(task.uni_code, task.category, task.url)
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    with open(fpath, "wb") as f:
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
    with open(content_path, "rb") as f:
        return f.read()
