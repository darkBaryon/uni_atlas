"""source_pages 任务注册表 —— 全项目唯一接触任务表的模块。

任务的生命周期都在这里：取到期任务、登记新发现的页面、
回写抓取状态（成功 / dead / moved / 失败留痕）。
"""
from datetime import datetime

import pymysql

import config

# 目录类 category：抓到内容后走 discover 流程（展开出新任务）而非实体解析
DISCOVER_CATEGORIES = {"program_catalog", "faculty_list", "module_catalog"}

_FREQ_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


def connect():
    return pymysql.connect(
        read_default_file=config.MY_CNF, host="127.0.0.1",
        database=config.DB_NAME, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=True,
    )


def ensure_university(conn, uconf):
    """--seed 用：universities 表没有该校则按 YAML 建行，返回 id。"""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM universities WHERE code=%s", (uconf.code,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute(
            "INSERT INTO universities (code, name_en, name_zh, country, city, website)"
            " VALUES (%s,%s,%s,%s,%s,%s)",
            (uconf.code, uconf.name, uconf.name_zh, uconf.country,
             uconf.city, uconf.website))
        return cur.lastrowid


def universities(conn):
    """code -> {id, code, name_en, website}"""
    with conn.cursor() as cur:
        cur.execute("SELECT id, code, name_en, website FROM universities WHERE is_active=1")
        return {r["code"]: r for r in cur.fetchall()}


def get_tasks(conn, uni_code=None, category=None, due_only=False,
              discover_only=False, limit=None):
    """取待抓任务。due_only: 仅 crawl_freq 周期已到期的; discover_only: 仅目录类。"""
    sql = ["SELECT sp.*, u.code AS uni_code FROM source_pages sp"
           " JOIN universities u ON u.id = sp.university_id"
           " WHERE sp.status = 'active' AND sp.fetch_method = 'html'"]
    args = []
    if uni_code:
        sql.append("AND u.code = %s"); args.append(uni_code)
    if category:
        sql.append("AND sp.category = %s"); args.append(category)
    if discover_only:
        sql.append("AND sp.category IN %s"); args.append(tuple(DISCOVER_CATEGORIES))
        # module_catalog 类里只有目录根页算 discover，模块详情页不算
        sql.append("AND NOT (sp.category='module_catalog' AND sp.url LIKE '%%/modules/%%')")
    if due_only:
        sql.append("AND sp.crawl_freq != 'manual' AND (sp.last_fetched_at IS NULL"
                   " OR sp.last_fetched_at < NOW() - INTERVAL"
                   " (CASE sp.crawl_freq WHEN 'daily' THEN 1 WHEN 'weekly' THEN 7"
                   " ELSE 30 END) DAY)")
    prio = ", ".join(f"'{c}'" for c in config.CATEGORY_PRIORITY)
    sql.append(f"ORDER BY FIELD(sp.category, {prio}),"
               " sp.last_fetched_at IS NOT NULL, sp.last_fetched_at, sp.id")
    if limit:
        sql.append("LIMIT %s"); args.append(int(limit))
    with conn.cursor() as cur:
        cur.execute(" ".join(sql), args)
        return cur.fetchall()


def count_skipped(conn, uni_code=None):
    """报告用：v1 不抓的 js_render / pdf 任务数。"""
    sql = ("SELECT sp.fetch_method, COUNT(*) n FROM source_pages sp"
           " JOIN universities u ON u.id = sp.university_id"
           " WHERE sp.status='active' AND sp.fetch_method IN ('js_render','pdf')")
    args = []
    if uni_code:
        sql += " AND u.code = %s"; args.append(uni_code)
    sql += " GROUP BY sp.fetch_method"
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return {r["fetch_method"]: r["n"] for r in cur.fetchall()}


def add_page(conn, university_id, category, url, title=None,
             crawl_freq="monthly", fetch_method="html", note=None):
    """登记新发现的页面；已存在则返回 (id, False)。"""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM source_pages WHERE university_id=%s AND url=%s",
                    (university_id, url))
        row = cur.fetchone()
        if row:
            return row["id"], False
        cur.execute(
            "INSERT INTO source_pages (university_id, category, url, title,"
            " fetch_method, crawl_freq, status, note)"
            " VALUES (%s,%s,%s,%s,%s,%s,'active',%s)",
            (university_id, category, url, title, fetch_method, crawl_freq, note))
        return cur.lastrowid, True


def mark_fetched(conn, page_id, content_hash=None, changed=False, note=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets, args = ["last_fetched_at=%s", "note=%s"], [now, note]
    if content_hash:
        sets.append("last_content_hash=%s"); args.append(content_hash)
    if changed:
        sets.append("last_changed_at=%s"); args.append(now)
    args.append(page_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE source_pages SET {', '.join(sets)} WHERE id=%s", args)


def mark_dead(conn, page_id, note=None):
    with conn.cursor() as cur:
        cur.execute("UPDATE source_pages SET status='dead', note=%s,"
                    " last_fetched_at=NOW() WHERE id=%s", (note, page_id))


def mark_moved(conn, page_id, redirect_to):
    with conn.cursor() as cur:
        cur.execute("UPDATE source_pages SET status='moved', redirect_to=%s,"
                    " last_fetched_at=NOW() WHERE id=%s", (redirect_to, page_id))


def mark_failed(conn, page_id, note):
    """抓取失败但页面未死：只留痕，last_fetched_at 不动，下轮仍到期重试。"""
    with conn.cursor() as cur:
        cur.execute("UPDATE source_pages SET note=%s WHERE id=%s", (note, page_id))
