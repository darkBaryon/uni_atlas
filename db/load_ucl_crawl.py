#!/usr/bin/env python3
"""把 UCL 计算机+商科爬取结果加载进 study_abroad 库。
输入: ucl_programs_full.json (39专业) + dsml_modules_full.json (14模块详情)
可重复执行 (upsert)。"""
import json, re, sys, hashlib, os
from datetime import datetime
import pymysql

SCRATCH = sys.argv[1] if len(sys.argv) > 1 else '.'
SNAP_DIR = '/Users/xinyue/VSCode/ws_2026/university/snapshots/ucl/programs'
FETCHED = '2026-07-03 21:45:00'
ENTRY = '2026'

conn = pymysql.connect(read_default_file='~/.my.cnf', host='127.0.0.1', database='study_abroad', charset='utf8mb4')
cur = conn.cursor()
cur.execute("SELECT id FROM universities WHERE code='ucl'")
UCL = cur.fetchone()[0]

def money(s):
    if not s: return None
    m = re.match(r'^£([\d,]+)$', s.strip())
    return float(m.group(1).replace(',', '')) if m else None

def dt(s):  # '20 Oct 2025' -> '2025-10-20'
    return datetime.strptime(s, '%d %b %Y').strftime('%Y-%m-%d') if s else None

def get_faculty(name, parent_id=None, level='faculty'):
    if not name: return None
    alias = {'Computer Science': 'UCL Computer Science'}  # 已有行的别名映射
    name = alias.get(name, name)
    cur.execute("SELECT id FROM faculties WHERE university_id=%s AND name_en=%s", (UCL, name))
    row = cur.fetchone()
    if row: return row[0]
    cur.execute("INSERT INTO faculties (university_id, parent_id, name_en, level) VALUES (%s,%s,%s,%s)",
                (UCL, parent_id, name, level))
    return cur.lastrowid

def get_source(url, category, note=None):
    cur.execute("SELECT id FROM source_pages WHERE university_id=%s AND url=%s", (UCL, url))
    row = cur.fetchone()
    if row: return row[0]
    cur.execute("""INSERT INTO source_pages (university_id, category, url, fetch_method, crawl_freq,
                   status, last_fetched_at, note) VALUES (%s,%s,%s,'html','monthly','active',%s,%s)""",
                (UCL, category, url, FETCHED, note))
    return cur.lastrowid

progs = json.load(open(f'{SCRATCH}/ucl_programs_full.json'))
dsml_mods = {m['code']: m for m in json.load(open(f'{SCRATCH}/dsml_modules_full.json'))}

n_prog = n_mod = n_link = n_dl = 0
for p in progs:
    fac_id = get_faculty(p['faculty'])
    dept_id = get_faculty(p['dept'], parent_id=fac_id, level='department') if p['dept'] and p['dept'] != p['faculty'] else fac_id
    level = 'UG' if p['level'] == 'UG' else 'PGT'
    crawl_failed = p.get('http_status') != 200 or not os.path.exists(f"{SNAP_DIR}/{p['url'].rstrip('/').split('/')[-1]}.html")

    sp_id = get_source(p['url'], 'program_detail', '抓取失败(Cloudflare挑战)，待重试' if crawl_failed else None)
    # 快照登记
    snap = f"{SNAP_DIR}/{p['url'].rstrip('/').split('/')[-1]}.html"
    if os.path.exists(snap):
        h = hashlib.sha256(open(snap, 'rb').read()).hexdigest()
        cur.execute("SELECT id FROM page_snapshots WHERE source_page_id=%s AND content_hash=%s", (sp_id, h))
        if not cur.fetchone():
            cur.execute("""INSERT INTO page_snapshots (source_page_id, fetched_at, http_status, content_hash, content_path, parsed_ok)
                           VALUES (%s,%s,200,%s,%s,1)""", (sp_id, FETCHED, h, snap))
        cur.execute("UPDATE source_pages SET last_content_hash=%s, last_changed_at=%s WHERE id=%s", (h, FETCHED, sp_id))

    cur.execute("""INSERT INTO programs (university_id, faculty_id, level, name_en, slug, url, ucas_code, duration, subject_tags)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE faculty_id=VALUES(faculty_id), url=VALUES(url),
                     duration=COALESCE(VALUES(duration), duration), id=LAST_INSERT_ID(id)""",
                (UCL, dept_id, level, p['name'], p['url'].rstrip('/').split('/')[-1], p['url'],
                 p.get('ucas'), p.get('duration'), json.dumps([p['dept'] or ''])))
    prog_id = cur.lastrowid
    n_prog += 1

    fee_uk, fee_intl = money(p.get('fee_uk')), money(p.get('fee_intl'))
    fee_note = None
    if p.get('fee_uk') and fee_uk is None:
        fee_note = f"学费非标准格式,原文: {p['fee_uk'][:200]}"
    if crawl_failed:
        fee_note = '抓取失败，学费/日期未获取'
    extra = {'fee_year_label': p.get('fee_year'), 'note': fee_note}
    cur.execute("""INSERT INTO program_details (program_id, entry_year, tuition_home, tuition_intl, currency,
                     entry_req_text, language_band, app_open_date, extra, source_page_id, fetched_at)
                   VALUES (%s,%s,%s,%s,'GBP',%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE tuition_home=VALUES(tuition_home), tuition_intl=VALUES(tuition_intl),
                     entry_req_text=COALESCE(VALUES(entry_req_text), entry_req_text),
                     language_band=COALESCE(VALUES(language_band), language_band),
                     extra=VALUES(extra), fetched_at=VALUES(fetched_at)""",
                (prog_id, ENTRY, fee_uk, fee_intl, p.get('entry_degree'),
                 ('level-' + p['english_level'][-1]) if p.get('english_level') else None,
                 dt(p['app_visa'][0]) if p.get('app_visa') else None,
                 json.dumps(extra, ensure_ascii=False), sp_id, FETCHED))

    # 截止日期
    cur.execute("DELETE FROM deadlines WHERE program_id=%s AND entry_year=%s", (prog_id, ENTRY))
    if p.get('app_visa'):
        cur.execute("""INSERT INTO deadlines (university_id, program_id, entry_year, audience, deadline_type, deadline_at, note, source_page_id, fetched_at)
                       VALUES (%s,%s,%s,'international','application',%s,'需签证申请者截止',%s,%s)""",
                    (UCL, prog_id, ENTRY, dt(p['app_visa'][1]) + ' 17:00:00', sp_id, FETCHED)); n_dl += 1
    if p.get('app_novisa'):
        cur.execute("""INSERT INTO deadlines (university_id, program_id, entry_year, audience, deadline_type, deadline_at, note, source_page_id, fetched_at)
                       VALUES (%s,%s,%s,'home','application',%s,'无需签证申请者截止',%s,%s)""",
                    (UCL, prog_id, ENTRY, dt(p['app_novisa'][1]) + ' 17:00:00', sp_id, FETCHED)); n_dl += 1

    # 模块 + 关联
    cur.execute("DELETE FROM program_modules WHERE program_id=%s", (prog_id,))
    for mtype, mods in (('core', p.get('modules_core', [])), ('optional', p.get('modules_optional', []))):
        for m in mods:
            det = dsml_mods.get(m.get('code'), {})
            credits = int(det['credits']) if det.get('credits') and det['credits'].isdigit() else None
            ass = det.get('assessment')
            if ass:  # 去重(页面按多个 delivery 重复列出)
                seen, ass2 = set(), []
                for a in ass:
                    k = (a['weight'], a['type'].lower())
                    if k not in seen: seen.add(k); ass2.append(a)
                ass = ass2
            extra_m = {}
            if det.get('leader'): extra_m['collected'] = 'module-catalogue 全字段'
            desc = det.get('description') or '仅名称/代码来自专业页；详情待抓取 module-catalogue'
            cur.execute("""INSERT INTO modules (university_id, faculty_id, code, name_en, credits, level, semester,
                             description, assessment, prerequisites, leader, extra, url, entry_year, fetched_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s)
                           ON DUPLICATE KEY UPDATE
                             credits=COALESCE(VALUES(credits), credits), leader=COALESCE(VALUES(leader), leader),
                             assessment=COALESCE(VALUES(assessment), assessment),
                             description=IF(VALUES(leader) IS NOT NULL, VALUES(description), description),
                             id=LAST_INSERT_ID(id)""",
                        (UCL, None, m.get('code'), m['name'], credits, det.get('level'), det.get('term'),
                         desc, json.dumps(ass) if ass else None, det.get('leader'),
                         json.dumps(extra_m) if extra_m else None, m.get('url'), ENTRY, FETCHED))
            mod_id = cur.lastrowid
            cur.execute("""INSERT IGNORE INTO program_modules (program_id, module_id, year_of_study, module_type)
                           VALUES (%s,%s,%s,%s)""",
                        (prog_id, mod_id, 1 if level == 'PGT' else None, mtype))
            n_link += 1
            n_mod += 1

conn.commit()
cur.execute("SELECT COUNT(*) FROM programs WHERE university_id=%s", (UCL,)); print('programs:', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM modules WHERE university_id=%s", (UCL,)); print('modules:', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM program_modules pm JOIN programs p ON p.id=pm.program_id WHERE p.university_id=%s", (UCL,)); print('program_modules:', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM deadlines WHERE university_id=%s", (UCL,)); print('deadlines:', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM page_snapshots"); print('snapshots:', cur.fetchone()[0])
print(f'processed {n_prog} programs, {n_dl} deadlines inserted')
