#!/usr/bin/env python3
"""把 study_abroad 数据库导出为 web/data/（index.js 索引 + 每校一个 <code>.js）。

用法:  python3 web/export.py
依赖:  pip install pymysql   (凭据自动读取 ~/.my.cnf)

导出结构：window.UNI_INDEX（总览摘要）+ window.UNI_DATA[code]（每校全量）:
  generated_at
  universities[]                 # 每校一个对象
    ├─ faculties[] calendar[] language_bands[] china_policy deadlines[]
    ├─ programs[]                # detail / deadlines / modules(引用模块id)
    ├─ modules{id: {...}}        # 模块全量: 大纲/负责人/考核/书单/课程内容
    └─ source_status             # 信息源健康度: active/dead/待采集
"""
import json
import os
from datetime import date, datetime
from decimal import Decimal

import pymysql

DB_NAME = "study_abroad"

# 库中以 JSON 字符串存储的列，导出时解析成对象
JSON_COLUMNS = {
    "extra", "subject_tags", "ielts_detail", "scholarships",
    "other_tests", "agent_list", "assessment", "research_areas", "plan",
}


def clean(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime | date):
            v = v.isoformat()
        elif isinstance(v, Decimal):
            v = float(v)
        elif k in JSON_COLUMNS and isinstance(v, str):
            try:
                v = json.loads(v)
            except ValueError:
                pass
        out[k] = v
    return out


def fetch_all(cur, sql, args=None):
    cur.execute(sql, args or ())
    return [clean(r) for r in cur.fetchall()]


def main():
    conn = pymysql.connect(
        read_default_file=os.path.expanduser("~/.my.cnf"),
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    cur = conn.cursor()

    universities = fetch_all(
        cur, "SELECT * FROM universities WHERE is_active=1 ORDER BY id")

    for uni in universities:
        uid = uni["id"]
        uni["faculties"] = fetch_all(
            cur, "SELECT * FROM faculties WHERE university_id=%s AND is_active=1 "
                 "ORDER BY parent_id IS NOT NULL, id", (uid,))
        uni["calendar"] = fetch_all(
            cur, "SELECT * FROM calendar_events WHERE university_id=%s "
                 "ORDER BY start_date", (uid,))
        uni["language_bands"] = fetch_all(
            cur, "SELECT * FROM language_bands WHERE university_id=%s "
                 "ORDER BY band_code", (uid,))
        policies = fetch_all(
            cur, "SELECT * FROM china_policies WHERE university_id=%s "
                 "ORDER BY entry_year DESC", (uid,))
        uni["china_policy"] = policies[0] if policies else None
        # 校级截止日期（不挂在具体专业下的）
        uni["deadlines"] = fetch_all(
            cur, "SELECT * FROM deadlines WHERE university_id=%s AND program_id IS NULL "
                 "ORDER BY deadline_at", (uid,))

        # ---- 模块全量（一次导出，专业里只放引用，避免 620 条关联重复膨胀）----
        modules = fetch_all(
            cur, "SELECT id, code, name_en, name_zh, credits, level, semester, faculty_id, "
                 "       description, assessment, prerequisites, leader, extra, url, entry_year "
                 "FROM modules WHERE university_id=%s AND is_active=1", (uid,))
        contents = fetch_all(
            cur, "SELECT mc.* FROM module_contents mc "
                 "JOIN modules m ON m.id=mc.module_id WHERE m.university_id=%s "
                 "ORDER BY mc.content_type, mc.seq_no, mc.id", (uid,))
        by_mod = {}
        for c in contents:
            by_mod.setdefault(c["module_id"], []).append(c)
        for m in modules:
            m["contents"] = by_mod.get(m["id"], [])
        uni["modules"] = {m["id"]: m for m in modules}

        # ---- 专业 ----
        uni["programs"] = fetch_all(
            cur, "SELECT * FROM programs WHERE university_id=%s AND is_active=1 "
                 "ORDER BY level, name_en", (uid,))
        for prog in uni["programs"]:
            pid = prog["id"]
            details = fetch_all(
                cur, "SELECT * FROM program_details WHERE program_id=%s "
                     "ORDER BY entry_year DESC", (pid,))
            prog["detail"] = details[0] if details else None
            prog["deadlines"] = fetch_all(
                cur, "SELECT * FROM deadlines WHERE program_id=%s "
                     "ORDER BY deadline_at", (pid,))
            prog["modules"] = fetch_all(
                cur, "SELECT pm.module_id, pm.module_type, pm.year_of_study, pm.note "
                     "FROM program_modules pm WHERE pm.program_id=%s", (pid,))
            prog["plans"] = fetch_all(
                cur, "SELECT variant_label, variant_label_zh, plan, source_url FROM program_plans "
                     "WHERE program_id=%s ORDER BY variant_label", (pid,))
            faculty = next((f for f in uni["faculties"] if f["id"] == prog["faculty_id"]), None)
            prog["faculty_name"] = (faculty or {}).get("name_zh") or (faculty or {}).get("name_en")

        # ---- 信息源健康度（页面上的"数据状态"板块）----
        uni["source_status"] = fetch_all(
            cur, "SELECT category, status, url, note, last_fetched_at "
                 "FROM source_pages WHERE university_id=%s "
                 "ORDER BY status='dead' DESC, note IS NOT NULL DESC, category", (uid,))

    conn.close()

    # ---- 按校拆分输出（与 config/parsers 同构）：data/index.js 总索引 +
    #      data/<code>.js 每校全量，学校数据由前端按需懒加载 ----
    # 写成 JS 全局变量而非 .json：file:// 下 fetch 被拦截，<script src> 不会
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)

    def dump(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    index = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
             "universities": []}
    total_kb = 0
    for uni in universities:
        code = uni["code"]
        index["universities"].append({
            "code": code, "name_en": uni["name_en"], "name_zh": uni["name_zh"],
            "country": uni["country"], "city": uni["city"],
            "term_system": uni["term_system"], "website": uni["website"],
            "extra": uni["extra"], "cn_student_note": uni["cn_student_note"],
            "n_programs": len(uni["programs"]),
            "n_modules": len(uni["modules"]),
            "has_calendar": bool(uni["calendar"]),
            "dead_sources": sum(1 for s in uni["source_status"]
                                if s["status"] == "dead"),
        })
        region_dir = os.path.join(data_dir, (uni["country"] or "other").lower())
        os.makedirs(region_dir, exist_ok=True)
        fpath = os.path.join(region_dir, f"{code}.js")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write("window.UNI_DATA = window.UNI_DATA || {};\n"
                    f"window.UNI_DATA[{dump(code)}] = {dump(uni)};\n")
        total_kb += os.path.getsize(fpath) // 1024
    with open(os.path.join(data_dir, "index.js"), "w", encoding="utf-8") as f:
        f.write("window.UNI_INDEX = " + dump(index) + ";\n")

    legacy = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.js")
    if os.path.exists(legacy):
        os.remove(legacy)

    n_prog = sum(len(u["programs"]) for u in universities)
    n_mod = sum(len(u["modules"]) for u in universities)
    print(f"OK: {len(universities)} 所大学, {n_prog} 个专业, {n_mod} 个模块"
          f" -> data/index.js + {len(universities)} 个校文件（共 {total_kb} KB）")


if __name__ == "__main__":
    main()
