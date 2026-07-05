#!/usr/bin/env python3
"""培养计划 PDF 解析 + 入库（新南试点，2026-07-06）。

新南工程学院的 progression checksheet 是 PDF（文本层干净、非扫描）：
按「专业代码 × 主修 × 起始学期」一份，内含逐年逐 term 的修课序列
+ 先修关系。用 pdfplumber 的**词坐标分列**（表头 Prerequisites/Credits
的 x 边界切三列）而非正则合并文本——后者对 "A or B" 二选一会误拆先修。

产出存 program_plans（新表，见 db/schema.sql）：一行一份计划，
plan 列是结构化 JSON（years[].items[]）。前端专业页渲染修课路线图。

用法:  python3 crawler/plans.py --uni unsw --url <PDF> --program-id N
       （试点手动指定；铺开时改为从 checksheet 目录页枚举）
"""
import argparse
import io
import json
import logging
import re
import sys

import requests

import logging_setup
import registry

logger = logging.getLogger(__name__)

CODE = re.compile(r"[A-Z]{2,4}\d{4}")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
      " (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def parse_plan(pdf_bytes):
    """PDF bytes → {'years': [{year, term, items:[{code?,label,prereq?,credits}]}]}。"""
    import pdfplumber
    years: list[dict] = []
    cur: dict | None = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            # 每页表头定列边界（个别页 Prerequisites 左移到 408，取本页实测值）
            xs = [w["x0"] for w in words if w["text"] == "Prerequisites"]
            x_pre = min(xs) - 8 if xs else 400
            xc = [w["x0"] for w in words if w["text"] == "Credits"]
            x_cr = min(xc) - 8 if xc else 510
            # 按 y(top) 聚成行
            rows: dict[int, list] = {}
            for w in words:
                rows.setdefault(round(w["top"]), []).append(w)
            for top in sorted(rows):
                ws = sorted(rows[top], key=lambda w: w["x0"])
                line = " ".join(w["text"] for w in ws).strip()
                ym = re.match(r"Year (\d+) Term (\d+)", line)
                if ym:
                    cur = {"year": int(ym.group(1)), "term": int(ym.group(2)), "items": []}
                    years.append(cur)
                    continue
                if cur is None or line.startswith("Course or Activity") or not line:
                    continue
                name = " ".join(w["text"] for w in ws if w["x0"] < x_pre).strip()
                prereq = " ".join(w["text"] for w in ws if x_pre <= w["x0"] < x_cr).strip()
                credit = " ".join(w["text"] for w in ws if w["x0"] >= x_cr).strip()
                if not name or not credit.isdigit():
                    continue
                # 滤 PDF 内的学位交叉引用行（"BE (Hons) ME Elec Eng [3736]"）——
                # 指向其他学位结构，非本计划课程/活动
                if re.search(r"\[\d{4}\]\s*$", name):
                    continue
                lead = CODE.match(name)
                item: dict = {"credits": int(credit)}
                if lead and "or" not in name.split(lead.group(0), 1)[1][:4].lower():
                    item["code"] = lead.group(0)
                    item["label"] = name[lead.end():].strip() or lead.group(0)
                else:
                    item["label"] = name          # 'A or B' 二选一 / 纯活动名整体留 label
                if prereq:
                    item["prereq"] = prereq
                cur["items"].append(item)
    return {"years": years}


# 培养计划占位活动/类别措辞词典（封闭集合，机翻会乱）
_PLAN_TERMS = [
    ("general education", "通识教育"), ("free electives", "自由选修"),
    ("free elective", "自由选修"), ("optional minors", "可选辅修"),
    ("optional minor", "可选辅修"), ("broadening discipline electives", "拓展学科选修"),
    ("recommended discipline electives", "推荐学科选修"),
    ("built environment electives", "建成环境选修"),
    ("engineering and technical management electives", "工程与技术管理选修"),
    ("discipline electives", "学科选修"), ("discipline elective", "学科选修"),
    ("computing electives", "计算机选修"), ("computing elective", "计算机选修"),
    ("prescribed electives", "指定选修"), ("prescribed elective", "指定选修"),
    ("technical electives", "技术选修"), ("professional electives", "专业选修"),
    ("electives", "选修课"), ("elective", "选修课"),
    ("thesis", "毕业论文"), ("capstone", "毕业设计"),
    ("industrial training", "实习"), ("work integrated learning", "带薪实习"),
    ("research project", "研究项目"), ("minor", "辅修"), ("major", "主修"),
    ("core courses", "核心课程"), ("core course", "核心课程"),
    ("specialisations", "专业方向"), ("specialisation", "专业方向"),
    ("masters project", "硕士项目"), ("coursework", "授课课程"),
    ("project", "项目"), ("courses", "课程"), ("course", "课程"),
    ("or", "或"), ("and", "和"),
]


def label_zh(text, modules_zh):
    """计划条目 label → 中文。带课程码的用 modules 表已翻名；
    'A or B' 二选一保留码只译连接词；类别名走词典。"""
    codes = CODE.findall(text)
    if codes:
        # 全是课程码的组合（A or B / A and B）：码不译，仅译连接词
        parts = re.split(r"\b(or|and)\b", text)
        out = []
        for p in parts:
            p = p.strip()
            if p in ("or", "and"):
                out.append("或" if p == "or" else "和")
            elif CODE.fullmatch(p) and modules_zh.get(p):
                out.append(f"{p} {modules_zh[p]}")
            elif p:
                out.append(p)
        return " ".join(out)
    s = re.sub(r"\bLevel (\d)\b", r"\1级", text, flags=re.I)   # Level 3 → 3级
    hit = False
    for en, zh in _PLAN_TERMS:                    # 长词组在前，整串多次替换
        new = re.sub(r"\b" + re.escape(en) + r"\b", zh, s, flags=re.I)
        if new != s:
            s, hit = new, True
    return re.sub(r"\s+", " ", s).strip() if hit and re.search(r"[一-鿿]", s) else None


def enrich_zh(conn, program_id, plan):
    """就地给 plan 各 item 补 label_zh：真课程用 modules.name_zh，活动走词典。"""
    with conn.cursor() as cur:
        cur.execute("SELECT code, name_zh FROM modules WHERE university_id="
                    "(SELECT university_id FROM programs WHERE id=%s)"
                    " AND code IS NOT NULL AND name_zh IS NOT NULL", (program_id,))
        mz = {r["code"]: r["name_zh"] for r in cur.fetchall()}
    for y in plan.get("years", []):
        for it in y.get("items", []):
            it.pop("label_zh", None)     # 幂等：先清旧值
            # 带码课程复用 modules.name_zh（与课程详情页一致，英主中辅显示）；
            # 占位活动/类别走词典。机翻个别技术课名不准是全库既有问题，用到再修。
            if it.get("code") and mz.get(it["code"]):
                it["label_zh"] = mz[it["code"]]
            elif not it.get("code"):
                z = label_zh(it.get("label", ""), mz)
                if z:
                    it["label_zh"] = z
    return plan


def variant_label(url):
    """PDF 文件名 → 干净的「主修方向 · 起始学期」标签（两种源格式都清）。
    如 '3707 - Bachelor Engineering (Honours) - Aerospace Engineering -
    AEROAH - T1 2026 Start' → 'Aerospace Engineering · T1 2026 入学'。"""
    from urllib.parse import unquote
    raw = unquote(url.split("/")[-1]).rsplit(".pdf", 1)[0]
    # 按分隔符切段（' - ' 或 连续破折号/下划线），每段内部空格保留
    segs = [re.sub(r"[-_\s]+", " ", s).strip()
            for s in re.split(r"\s*-\s*-\s*|\s+-\s+|_{2,}|-{2,}", raw)]
    segs = [s for s in segs if s]
    # 起始学期段
    term = ""
    for i, s in enumerate(segs):
        m = re.search(r"\bT([123])\b.*?(20\d{2})", s, re.I)
        if m:
            term = f"T{m.group(1)} {m.group(2)} 入学"
            segs = segs[:i]          # 学期段及其后（Start）截掉
            break
    # 丢：4 位代码段、学位名段（Bachelor/Master…）、纯主修代码段（短且无空格）
    def junk(s):
        return (re.fullmatch(r"\d{4}", s) or re.match(r"(bachelor|master)\b", s, re.I)
                or re.match(r"1st yr", s, re.I)
                or (len(s) <= 8 and " " not in s and re.fullmatch(r"[A-Za-z]+\d*", s)))
    majors = [s for s in segs if not junk(s)]
    major = majors[-1].title() if majors else (segs[-1].title() if segs else "")
    label = (major + (" · " + term if term else "")).strip(" ·")
    return label or "培养计划"


# 主修方向（工程学科）中文词典：先长后短，"X Engineering"→"X工程"由后缀规则兜底
_MAJOR_TERMS = [
    ("mine geotechnical", "矿山岩土"), ("geotechnical", "岩土"),
    ("geoenergy and geostorage", "地热能与地质封存"), ("geoenergy", "地热能"),
    ("geostorage", "地质封存"), ("geo eng and eng geology", "地质工程与工程地质"),
    ("aerospace", "航空航天"), ("bioinformatics", "生物信息"),
    ("biomedical", "生物医学"), ("chemical product", "化工产品"),
    ("chemical", "化学"), ("civil", "土木"), ("computer networks", "计算机网络"),
    ("computer science", "计算机科学"), ("computer engineering", "计算机工程"),
    ("computer", "计算机"), ("electrical", "电气"), ("environmental", "环境"),
    ("mechanical", "机械"), ("mechatronic", "机电"), ("mechatronics", "机电"),
    ("mining", "采矿"), ("nuclear", "核"), ("petroleum", "石油"),
    ("photovoltaics and solar energy", "光伏与太阳能"), ("photovoltaics", "光伏"),
    ("renewable energy", "可再生能源"), ("renewable", "可再生能源"),
    ("robotics and mechatronics", "机器人与机电"), ("robotics", "机器人"),
    ("software", "软件"), ("structural", "结构"), ("surveying", "测绘"),
    ("telecommunications", "电信"), ("transport", "交通运输"),
    ("water wastewater and waste", "水与污废水"), ("water", "水"),
    ("quantum", "量子"), ("space systems", "空间系统"),
    ("adv manufacturing", "先进制造"), ("advanced manufacturing", "先进制造"),
    ("manufacturing", "制造"), ("food process", "食品加工"),
    ("food science and technology", "食品科学与技术"),
    ("food science and nutrition", "食品科学与营养"), ("food science", "食品科学"),
    ("energy systems", "能源系统"), ("embedded systems", "嵌入式系统"),
    ("systems and control", "系统与控制"), ("sustainable systems", "可持续系统"),
    ("security engineering", "安全工程"), ("cyber security", "网络安全"),
    ("engineering science", "工程科学"), ("space", "空间"),
    ("artificial intelligence", "人工智能"), ("database systems", "数据库系统"),
    ("information technology", "信息技术"), ("internetworking", "网络互联"),
    ("programming languages", "编程语言"), ("computational biology", "计算生物学"),
    ("project management", "项目管理"), ("photovoltaic", "光伏"),
    ("commerce specialisation", "商科方向"), ("commerce specialisations", "商科方向"),
]
def major_zh(label):
    """主修方向英文名 → 中文（词典子串匹配学科词根，工程类补'工程'后缀）。
    子串匹配天然容忍尾部残留 spec 码；词典未覆盖返回 None（前端回退英文）。"""
    low = re.sub(r"\s*·.*$", "", label).strip().lower()   # 去 ' · T1 …' 尾
    is_eng = "engineering" in low or re.search(r"\beng\b", low)
    for en, zh in _MAJOR_TERMS:                       # 长词根在前
        if en in low:
            done = zh.endswith(("工程", "技术", "科学", "系统", "方向",
                                "能源", "安全", "制造", "智能", "语言",
                                "网络", "生物学", "管理", "互联"))
            return zh + "工程" if is_eng and not done else zh
    return None


def variant_zh(label):
    """完整中文变体标签：'电气工程 · T1 2026 入学'（学期段照抄）。"""
    mz = major_zh(label)
    if not mz:
        return None
    tm = re.search(r"·\s*(.+)$", label)
    return f"{mz} · {tm.group(1).strip()}" if tm else mz


def load_plan(conn, program_id, entry_year, plan, url):
    label = variant_label(url)
    zh = variant_zh(label)
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM program_plans WHERE program_id=%s"
                    " AND variant_label=%s AND entry_year=%s",
                    (program_id, label, entry_year))
        row = cur.fetchone()
        payload = json.dumps(plan, ensure_ascii=False)
        if row:
            cur.execute("UPDATE program_plans SET plan=%s, source_url=%s,"
                        " variant_label_zh=%s WHERE id=%s",
                        (payload, url, zh, row["id"]))
        else:
            cur.execute("INSERT INTO program_plans (program_id, variant_label,"
                        " variant_label_zh, entry_year, plan, source_url)"
                        " VALUES (%s,%s,%s,%s,%s,%s)",
                        (program_id, label, zh, entry_year, payload, url))
    conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="培养计划 PDF 直链")
    ap.add_argument("--program-id", type=int, required=True)
    ap.add_argument("--entry-year", default="2026")
    args = ap.parse_args()
    logging_setup.setup()
    body = requests.get(args.url, headers={"User-Agent": UA}, timeout=60).content
    plan = parse_plan(body)
    n = sum(len(y["items"]) for y in plan["years"])
    if not n:
        logger.error("解析出 0 条目，PDF 版式可能不同，未入库")
        return 1
    conn = registry.connect()
    enrich_zh(conn, args.program_id, plan)   # 活动/类别补中文
    load_plan(conn, args.program_id, args.entry_year, plan, args.url)
    logger.info("培养计划入库：program %d，%d 学期 %d 条目",
                args.program_id, len(plan["years"]), n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
