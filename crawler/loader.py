"""装载器：标准数据对象 -> MySQL upsert，新旧值不同 -> change_log。

原则：
- 解析出 None 的字段不覆盖库中已有值（抓取退化不吃掉旧数据）；
- 关键字段（学费/截止/学分/负责人）变化写 change_log，供报告播报。
"""
import json
from datetime import datetime

import config

# 各实体记入 change_log 的字段
TRACKED = {
    "program_detail": ("tuition_home", "tuition_intl", "entry_req_text",
                       "language_band", "ielts_overall", "app_open_date"),
    "module": ("credits", "leader", "assessment", "semester"),
    "deadline": ("deadline_at",),
}

class Loader:
    def __init__(self, conn, university_id, uni_code=None):
        self.conn = conn
        self.uid = university_id
        uconf = config.uni(uni_code) if uni_code else None
        self.faculty_zh = uconf.faculties if uconf else {}   # 英文名 -> 中文名
        self.faculty_alias = uconf.faculty_alias if uconf else {}  # 页面叫法 -> 官方名
        self.faculty_overrides = uconf.faculty_overrides if uconf else {}  # slug -> 官方名（人工整理）
        self.stats = {"programs": 0, "modules": 0, "deadlines": 0,
                      "calendar": 0, "changes": 0}
        self.changes = []          # 报告用: (entity, name, field, old, new)

    def _cur(self):
        return self.conn.cursor()

    def _log(self, entity_type, entity_id, change_type, field, old, new,
             snapshot_id, label=""):
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO change_log (university_id, entity_type, entity_id,"
                " change_type, field_name, old_value, new_value, snapshot_id,"
                " detected_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (self.uid, entity_type, entity_id, change_type, field,
                 None if old is None else str(old)[:2000],
                 None if new is None else str(new)[:2000],
                 snapshot_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.stats["changes"] += 1
        if change_type == "update":
            self.changes.append((entity_type, label, field, old, new))

    def _diff_update(self, table, entity_type, row_id, tracked, new_values,
                     snapshot_id, label=""):
        """按字段对比并更新；None 不覆盖；tracked 字段的变化写 change_log。"""
        cols = [k for k, v in new_values.items() if v is not None]
        if not cols:
            return
        with self._cur() as cur:
            cur.execute(f"SELECT {', '.join(cols)} FROM {table} WHERE id=%s", (row_id,))
            old = cur.fetchone() or {}
        to_set = {}
        for k in cols:
            new_v, old_v = new_values[k], old.get(k)
            if _neq(old_v, new_v):
                to_set[k] = new_v
                if k in tracked and old_v is not None:
                    self._log(entity_type, row_id, "update", k, old_v, new_v,
                              snapshot_id, label)
        if to_set:
            sets = ", ".join(f"{k}=%s" for k in to_set)
            with self._cur() as cur:
                cur.execute(f"UPDATE {table} SET {sets} WHERE id=%s",
                            (*to_set.values(), row_id))

    # ---------------- faculty ----------------
    def faculty_id(self, name, parent_id=None, level="faculty"):
        if not name:
            return None
        name = self.faculty_alias.get(name, name)
        name_zh = self.faculty_zh.get(name)
        with self._cur() as cur:
            cur.execute("SELECT id, name_zh FROM faculties WHERE university_id=%s AND name_en=%s",
                        (self.uid, name))
            row = cur.fetchone()
            if row:
                if name_zh and not row["name_zh"]:   # 配置里有中文名而库里还没有 → 补上
                    cur.execute("UPDATE faculties SET name_zh=%s WHERE id=%s",
                                (name_zh, row["id"]))
                return row["id"]
            cur.execute("INSERT INTO faculties (university_id, parent_id, name_en,"
                        " name_zh, level) VALUES (%s,%s,%s,%s,%s)",
                        (self.uid, parent_id, name, name_zh, level))
            return cur.lastrowid

    def faculty_from_note(self, note):
        """目录页学位卡的院系文本: 'Faculty of X' 或 'Faculty of X | Dept'。"""
        if not note:
            return None
        parts = [s.strip() for s in note.split("|") if s.strip()]
        if not parts:
            return None
        fac = self.faculty_id(parts[0])
        if len(parts) > 1 and parts[1] != parts[0]:
            return self.faculty_id(parts[1], parent_id=fac, level="department")
        return fac

    # ---------------- program ----------------
    def load_program(self, p, source_page_id, snapshot_id, faculty_note=None):
        fac_id = None
        slug_key = p.url.rstrip("/").split("/")[-1]
        if slug_key in self.faculty_overrides:   # 人工整理层优先（页面无信号的专业）
            fac_id = self.faculty_id(self.faculty_overrides[slug_key])
        elif p.faculty or p.dept:
            fac = self.faculty_id(p.faculty)
            fac_id = (self.faculty_id(p.dept, parent_id=fac, level="department")
                      if p.dept and p.dept != p.faculty else fac)
        if fac_id is None:
            fac_id = self.faculty_from_note(faculty_note)

        slug = p.url.rstrip("/").split("/")[-1]
        name_en = _trunc(p.name_en, 255)
        with self._cur() as cur:
            cur.execute("SELECT id FROM programs WHERE university_id=%s AND level=%s"
                        " AND name_en=%s", (self.uid, p.level, name_en))
            row = cur.fetchone()
            if not row:   # 名称对不上时按 URL 兜底（子页数据回填、页面改名等场景防重复）
                cur.execute("SELECT id FROM programs WHERE university_id=%s AND url=%s",
                            (self.uid, p.url))
                row = cur.fetchone()
            if row:
                prog_id = row["id"]
                self._diff_update(
                    "programs", "program", prog_id, (),
                    {"faculty_id": fac_id, "url": p.url, "slug": slug,
                     "ucas_code": p.ucas_code, "duration": _trunc(p.duration, 64)},
                    snapshot_id, p.name_en)
            else:
                cur.execute(
                    "INSERT INTO programs (university_id, faculty_id, level, name_en,"
                    " slug, url, ucas_code, duration) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
                    " ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id),"
                    " faculty_id=COALESCE(VALUES(faculty_id), faculty_id),"
                    " slug=VALUES(slug), url=VALUES(url),"
                    " ucas_code=COALESCE(VALUES(ucas_code), ucas_code),"
                    " duration=COALESCE(VALUES(duration), duration)",
                    (self.uid, fac_id, p.level, name_en, slug, p.url, p.ucas_code,
                     _trunc(p.duration, 64)))
                prog_id = cur.lastrowid
                if cur.rowcount == 1:
                    self._log("program", prog_id, "insert", None, None,
                              p.name_en, snapshot_id)
        self.stats["programs"] += 1

        # ---- program_details（按申请季）----
        extra = {}
        if p.fee_year_label:
            extra["fee_year_label"] = p.fee_year_label
        if p.campus:
            extra["campus"] = p.campus
        if p.notes:
            extra["parse_notes"] = p.notes
        detail_vals = {
            "tuition_home": p.tuition_home, "tuition_intl": p.tuition_intl,
            "entry_req_text": p.entry_req_text, "language_band": p.language_band,
            "ielts_overall": p.ielts_overall,
            "ielts_detail": (json.dumps({"minimum_each": p.ielts_min_each})
                             if p.ielts_min_each else None),
            "app_open_date": p.app_open_date,
            "extra": json.dumps(extra, ensure_ascii=False) if extra else None,
            "source_page_id": source_page_id,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with self._cur() as cur:
            cur.execute("SELECT id FROM program_details WHERE program_id=%s"
                        " AND entry_year=%s", (prog_id, p.entry_year))
            row = cur.fetchone()
            if row:
                self._diff_update("program_details", "program_detail", row["id"],
                                  TRACKED["program_detail"], detail_vals,
                                  snapshot_id, p.name_en)
            else:
                cols = ["program_id", "entry_year", "currency"] + list(detail_vals)
                vals = [prog_id, p.entry_year, p.currency] + list(detail_vals.values())
                updates = ", ".join(
                    f"{c}=COALESCE(VALUES({c}), {c})"
                    for c in cols if c not in ("program_id", "entry_year"))
                cur.execute(f"INSERT INTO program_details ({', '.join(cols)})"
                            f" VALUES ({', '.join(['%s']*len(vals))})"
                            f" ON DUPLICATE KEY UPDATE {updates}", vals)

        for d in p.deadlines:
            self.load_deadline(d, source_page_id, snapshot_id,
                               program_id=prog_id, label=p.name_en)

        # ---- 模块关联（页面给出非空模块表时整表替换）----
        if p.modules:
            with self._cur() as cur:
                cur.execute("DELETE FROM program_modules WHERE program_id=%s", (prog_id,))
            for ref in p.modules:
                mod_id = self._module_stub(ref, p.entry_year, source_page_id)
                with self._cur() as cur:
                    cur.execute("INSERT IGNORE INTO program_modules (program_id,"
                                " module_id, year_of_study, module_type)"
                                " VALUES (%s,%s,%s,%s)",
                                (prog_id, mod_id,
                                 1 if p.level == "PGT" else None, ref.module_type))
        return prog_id

    # ---------------- module ----------------
    def _find_module(self, cur, code, name, entry_year):
        if code:
            cur.execute("SELECT id FROM modules WHERE university_id=%s AND code=%s"
                        " AND entry_year=%s", (self.uid, code, entry_year))
        else:
            cur.execute("SELECT id FROM modules WHERE university_id=%s AND name_en=%s"
                        " AND entry_year=%s AND code IS NULL",
                        (self.uid, name, entry_year))
        row = cur.fetchone()
        return row["id"] if row else None

    def _module_stub(self, ref, entry_year, source_page_id):
        """专业页上的模块引用：只建骨架行（名称/代码/链接），详情由模块页任务补齐。"""
        with self._cur() as cur:
            mod_id = self._find_module(cur, ref.code, ref.name, entry_year)
            if mod_id:
                return mod_id
            cur.execute(
                "INSERT INTO modules (university_id, code, name_en, url, entry_year,"
                " description, source_page_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (self.uid, ref.code, ref.name, ref.url, entry_year,
                 "仅名称/代码来自专业页；详情待抓取 module-catalogue", source_page_id))
            return cur.lastrowid

    def load_module(self, m, source_page_id, snapshot_id):
        vals = {
            "credits": m.credits, "level": _trunc(m.level, 16),
            "semester": _trunc(m.semester, 32),
            "leader": _trunc(m.leader, 255),
            "prerequisites": _trunc(m.prerequisites, 512),
            "assessment": json.dumps(m.assessment) if m.assessment else None,
            "description": m.description, "url": m.url,
            "source_page_id": source_page_id,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with self._cur() as cur:
            mod_id = self._find_module(cur, m.code, m.name_en, m.entry_year)
            if mod_id:
                # 骨架行的占位 description 允许被真大纲覆盖
                cur.execute("SELECT description FROM modules WHERE id=%s", (mod_id,))
                old_desc = (cur.fetchone() or {}).get("description") or ""
                if old_desc.startswith("仅名称/代码来自专业页"):
                    with self._cur() as c2:
                        c2.execute("UPDATE modules SET description=NULL WHERE id=%s",
                                   (mod_id,))
                self._diff_update("modules", "module", mod_id, TRACKED["module"],
                                  vals, snapshot_id, m.code or m.name_en)
            else:
                cols = ["university_id", "code", "name_en", "entry_year"] + list(vals)
                v = [self.uid, m.code, m.name_en, m.entry_year] + list(vals.values())
                cur.execute(f"INSERT INTO modules ({', '.join(cols)})"
                            f" VALUES ({', '.join(['%s']*len(v))})", v)
                mod_id = cur.lastrowid
        self.stats["modules"] += 1
        return mod_id

    # ---------------- deadline ----------------
    def load_deadline(self, d, source_page_id, snapshot_id,
                      program_id=None, label=""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._cur() as cur:
            cur.execute(
                "SELECT id, deadline_at FROM deadlines WHERE university_id=%s"
                " AND (program_id <=> %s) AND entry_year=%s AND audience=%s"
                " AND deadline_type=%s AND (round_no <=> %s) LIMIT 1",
                (self.uid, program_id, d.entry_year, d.audience, d.deadline_type,
                 getattr(d, "round_no", None)))
            row = cur.fetchone()
            if row:
                if _neq(row["deadline_at"], d.deadline_at):
                    self._log("deadline", row["id"], "update", "deadline_at",
                              row["deadline_at"], d.deadline_at, snapshot_id,
                              label or d.note)
                    cur.execute("UPDATE deadlines SET deadline_at=%s, note=%s,"
                                " source_page_id=%s, fetched_at=%s WHERE id=%s",
                                (d.deadline_at, d.note, source_page_id, now, row["id"]))
                else:
                    cur.execute("UPDATE deadlines SET fetched_at=%s WHERE id=%s",
                                (now, row["id"]))
            else:
                cur.execute(
                    "INSERT INTO deadlines (university_id, program_id, entry_year,"
                    " audience, deadline_type, round_no, deadline_at, note,"
                    " source_page_id, fetched_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (self.uid, program_id, d.entry_year, d.audience,
                     d.deadline_type, getattr(d, "round_no", None),
                     d.deadline_at, d.note, source_page_id, now))
                self._log("deadline", cur.lastrowid, "insert", None, None,
                          f"{label} {d.deadline_at}".strip(), snapshot_id)
        self.stats["deadlines"] += 1

    # ---------------- calendar ----------------
    def load_calendar(self, c, source_page_id, snapshot_id):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._cur() as cur:
            cur.execute(
                "SELECT id, start_date, end_date FROM calendar_events"
                " WHERE university_id=%s AND academic_year=%s AND calendar_track=%s"
                " AND event_type=%s AND name=%s",
                (self.uid, c.academic_year, c.calendar_track, c.event_type, c.name))
            row = cur.fetchone()
            if row:
                if _neq(row["start_date"], c.start_date) or _neq(row["end_date"], c.end_date):
                    self._log("calendar_event", row["id"], "update", "dates",
                              f"{row['start_date']}~{row['end_date']}",
                              f"{c.start_date}~{c.end_date}", snapshot_id, c.name)
                    cur.execute("UPDATE calendar_events SET start_date=%s, end_date=%s,"
                                " source_page_id=%s, fetched_at=%s WHERE id=%s",
                                (c.start_date, c.end_date, source_page_id, now, row["id"]))
            else:
                cur.execute(
                    "INSERT INTO calendar_events (university_id, academic_year,"
                    " calendar_track, event_type, name, start_date, end_date,"
                    " source_page_id, fetched_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (self.uid, c.academic_year, c.calendar_track, c.event_type,
                     c.name, c.start_date, c.end_date, source_page_id, now))
        self.stats["calendar"] += 1


def _trunc(v, n):
    """VARCHAR 防御截断：页面偶有超长文本（如一页列多种学制），截断并保留可读性。"""
    if isinstance(v, str) and len(v) > n:
        return v[: n - 1] + "…"
    return v


def _neq(old, new):
    """跨类型宽松比较：'46700.00' vs 46700.0、date vs 'YYYY-MM-DD' 视为相等。"""
    if old is None or new is None:
        return old is not new
    try:
        return float(old) != float(new)
    except (TypeError, ValueError):
        return str(old).strip() != str(new).strip()
