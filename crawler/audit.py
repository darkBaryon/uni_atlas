#!/usr/bin/env python3
"""数据体检：把「人工撞见问题」固化成逐校断言矩阵。

用法:  python3 crawler/audit.py [--uni CODE] [--quiet]
退出码: 有红灯=1（供 run.sh / cron 判停），否则 0。

规则来源＝历次人工验收发现的问题类型（2026-07 逐校验收实战）：
课程量下限 / 链接·中文名·归属覆盖率 / 垃圾名黑名单 / 译文复读退化 /
校历时效与考试期 / 漏抓任务 / 重复代码 / 失效源占比。
每校差异（如布里斯托课程被 WAF 挡、谢菲无中央目录）写在校 YAML 的
`expect:` 段，不改代码：

    expect:
      modules_min: 3000        # 该校课程名单的合理下限
      module_faculty_pct: 90   # 归属率下限（默认 60）
      modules_skip: "目录被 FortiWeb 硬挡"   # 整段跳过并注明原因
"""
import argparse
import logging
import sys

import config
import logging_setup
import registry

logger = logging.getLogger(__name__)

# 全局默认阈值（校 YAML expect 段可按键覆盖）
DEFAULTS = {
    "modules_min": 1,            # 至少有课程名单（除非 modules_skip）
    "module_url_pct": 90,        # 课程带官方链接
    "module_zh_pct": 90,         # 课程带中文名
    "module_faculty_pct": 60,    # 课程带院系归属
    "programs_min": 100,
    "program_faculty_pct": 90,   # 专业归属
    "calendar_future": 1,        # 今天之后仍有校历事件
    "exam_periods": 1,           # 考试期/补考期事件（辅导排班核心）
    "dead_src_pct": 25,          # 失效源占比上限
}
JUNK_NAME_RE = r"^[^A-Za-z0-9]|^(Modules?|Year [0-9]|Semester [0-9]|Optional|Core)$"

GREEN, YELLOW, RED = "✓", "△", "✗"


def _expect(uconf, key):
    exp = getattr(uconf, "expect", None) or {}
    return exp.get(key, DEFAULTS[key])


def _one(cur, sql, args=()):
    cur.execute(sql, args)
    row = cur.fetchone()
    return list(row.values())[0] if row else None


def audit_uni(cur, uid, uconf):
    """一所学校的断言清单 -> [(灯, 规则, 实测)]。"""
    out = []
    exp = getattr(uconf, "expect", None) or {}

    def check(ok, rule, actual, warn=False):
        out.append((GREEN if ok else (YELLOW if warn else RED), rule, actual))

    # ---- 课程名单 ----
    if exp.get("modules_skip"):
        out.append((YELLOW, "课程名单（跳过）", exp["modules_skip"]))
    else:
        n = _one(cur, "SELECT COUNT(*) c FROM modules WHERE university_id=%s"
                      " AND is_active=1", (uid,))
        check(n >= _expect(uconf, "modules_min"),
              f"课程数 ≥ {_expect(uconf, 'modules_min')}", n)
        if n:
            for col, key, label in (("url", "module_url_pct", "链接"),
                                    ("name_zh", "module_zh_pct", "中文名"),
                                    ("faculty_id", "module_faculty_pct", "归属")):
                pct = _one(cur, f"SELECT ROUND(100*SUM({col} IS NOT NULL)/COUNT(*)) c"
                                " FROM modules WHERE university_id=%s AND is_active=1",
                           (uid,))
                check(pct >= _expect(uconf, key), f"课程{label} ≥ {_expect(uconf, key)}%",
                      f"{pct}%")
            junk = _one(cur, "SELECT COUNT(*) c FROM modules WHERE university_id=%s"
                             " AND is_active=1 AND name_en REGEXP %s",
                        (uid, JUNK_NAME_RE))
            check(junk == 0, "垃圾课程名 = 0", junk)
            dup = _one(cur, "SELECT COUNT(*) c FROM (SELECT code FROM modules"
                            " WHERE university_id=%s AND is_active=1 AND code IS NOT NULL"
                            " GROUP BY code, entry_year HAVING COUNT(*)>1) t", (uid,))
            check(dup == 0, "重复课程代码 = 0", dup)
            fat = _one(cur, "SELECT COUNT(*) c FROM modules WHERE university_id=%s"
                            " AND is_active=1 AND name_zh IS NOT NULL"
                            " AND CHAR_LENGTH(name_zh) > GREATEST(60, 3*CHAR_LENGTH(name_en))",
                       (uid,))
            check(fat == 0, "复读退化译文 = 0", fat)

    # ---- 专业 ----
    n = _one(cur, "SELECT COUNT(*) c FROM programs WHERE university_id=%s AND is_active=1",
             (uid,))
    check(n >= _expect(uconf, "programs_min"), f"专业数 ≥ {_expect(uconf, 'programs_min')}", n)
    if n:
        pct = _one(cur, "SELECT ROUND(100*SUM(faculty_id IS NOT NULL)/COUNT(*)) c"
                        " FROM programs WHERE university_id=%s AND is_active=1", (uid,))
        check(pct >= _expect(uconf, "program_faculty_pct"),
              f"专业归属 ≥ {_expect(uconf, 'program_faculty_pct')}%", f"{pct}%")

    # ---- 校历（辅导核心：还得有未来的，且有考试期）----
    fut = _one(cur, "SELECT COUNT(*) c FROM calendar_events WHERE university_id=%s"
                    " AND start_date >= CURDATE()", (uid,))
    check(fut >= _expect(uconf, "calendar_future"), "未来校历事件 ≥ 1", fut)
    ex = _one(cur, "SELECT COUNT(*) c FROM calendar_events WHERE university_id=%s"
                   " AND event_type IN ('exam_period','resit_period')"
                   " AND start_date >= CURDATE()", (uid,))
    check(ex >= _expect(uconf, "exam_periods"), "未来考试期 ≥ 1", ex,
          warn=bool(exp.get("exam_skip")))

    # ---- 采集链路 ----
    miss = _one(cur, "SELECT COUNT(*) c FROM source_pages WHERE university_id=%s"
                     " AND status='active' AND crawl_freq!='manual'"
                     " AND last_fetched_at IS NULL", (uid,))
    check(miss == 0, "从未抓过的任务 = 0（漏抓）", miss)
    dead = _one(cur, "SELECT ROUND(100*SUM(status='dead')/COUNT(*)) c"
                     " FROM source_pages WHERE university_id=%s", (uid,))
    check((dead or 0) <= _expect(uconf, "dead_src_pct"),
          f"失效源 ≤ {_expect(uconf, 'dead_src_pct')}%", f"{dead}%")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uni", help="只体检某校")
    ap.add_argument("--quiet", action="store_true", help="只输出红黄灯")
    args = ap.parse_args()
    logging_setup.setup()
    conn = registry.connect()
    reds = 0
    with conn.cursor() as cur:
        cur.execute("SELECT id, code, name_zh FROM universities WHERE is_active=1"
                    + (" AND code=%s" if args.uni else "") + " ORDER BY code",
                    (args.uni,) if args.uni else ())
        unis = cur.fetchall()
        for u in unis:
            uconf = config.uni(u["code"])
            rows = audit_uni(cur, u["id"], uconf)
            bad = [r for r in rows if r[0] != GREEN]
            reds += sum(1 for r in rows if r[0] == RED)
            head = f"== {u['code']} {u['name_zh'] or ''} " \
                   f"[{sum(1 for r in rows if r[0]==GREEN)}/{len(rows)} 绿]"
            logger.info(head)
            for light, rule, actual in (bad if args.quiet else rows):
                logger.info("  %s %-24s %s", light, rule, actual)
    logger.info("体检完成：红灯 %d 项%s", reds, "（需要处理）" if reds else "")
    return 1 if reds else 0


if __name__ == "__main__":
    sys.exit(main())
