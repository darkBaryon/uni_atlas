"""解析器黄金测试：真实快照 → 解析输出与锁定的黄金文件逐字段对比。

改了解析器/公共提取器后跑本测试，任何字段变化都会显式暴露；
若变化是有意的，UPDATE_GOLDEN=1 pytest 重新锁定。
"""
import json
import os

import pytest

FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
GOLD_DIR = os.path.join(os.path.dirname(__file__), "golden")
MANIFEST = json.load(open(os.path.join(FIX_DIR, "manifest.json"), encoding="utf-8"))
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def _digest(result):
    """ParseResult → 可比对的纯数据摘要（只锁关键字段，忽略易变噪声）。"""
    out = {}
    if result.programs:
        out["programs"] = [{
            "name_en": p.name_en, "level": p.level, "entry_year": p.entry_year,
            "tuition_home": p.tuition_home, "tuition_intl": p.tuition_intl,
            "ielts": [p.ielts_overall, p.ielts_min_each],
            "language_band": p.language_band,
            "ucas_code": p.ucas_code, "duration": p.duration,
            "dept": p.dept, "faculty": p.faculty,
            "entry_req_head": (p.entry_req_text or "")[:80] or None,
            "deadlines": [[d.audience, d.deadline_type, d.deadline_at, d.round_no]
                          for d in p.deadlines],
            "n_modules": len(p.modules),
        } for p in result.programs]
    if result.modules:
        out["modules"] = [{
            "code": m.code, "name_en": m.name_en, "credits": m.credits,
            "level": m.level, "semester": m.semester, "leader": m.leader,
            "assessment": m.assessment,
        } for m in result.modules]
    if result.calendar:
        out["calendar"] = [[c.academic_year, c.event_type, c.name,
                            c.start_date, c.end_date] for c in result.calendar]
    if result.discovered:
        out["n_discovered"] = len(result.discovered)
    if result.notes:
        out["notes"] = result.notes
    return out


@pytest.mark.parametrize("item", MANIFEST, ids=lambda m: m["file"][:60])
def test_parser_golden(item):
    import parsers  # noqa: F401  触发注册
    from parsers.base import get_parser

    fn = get_parser(item["uni"], item["category"])
    assert fn, f"{item['uni']}/{item['category']} 无解析器"
    html = open(os.path.join(FIX_DIR, item["file"]), "rb").read()
    got = _digest(fn(html, item["url"]))

    gold_path = os.path.join(GOLD_DIR, item["file"].rsplit(".", 1)[0] + ".json")
    if UPDATE or not os.path.exists(gold_path):
        json.dump(got, open(gold_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1, sort_keys=True)
        if UPDATE:
            pytest.skip("golden 已更新")
    want = json.load(open(gold_path, encoding="utf-8"))
    assert got == want
