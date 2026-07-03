"""目录页展开：把解析出的 DiscoveredPage 与模块引用登记进 source_pages。

范围策略在这里落地（config.FOCUS_DEPTS / CRAWL_MODULE_DETAILS）：
范围内 → 按解析器建议的周期自动抓；范围外 → 登记在册但 crawl_freq='manual'，
--due 永远不会选中，需要时可 --category 定向抓。
"""
import config
import registry


def _in_focus(uni_code, dept_note):
    """dept_note: 目录页学位卡的院系文本，如 'Faculty of X | Computer Science'。"""
    focus = config.FOCUS_DEPTS.get(uni_code)
    if not focus:          # 未配置范围的学校 = 全部在范围内
        return True
    return bool(dept_note) and any(d in dept_note for d in focus)


def register_discovered(conn, university_id, uni_code, discovered):
    """ParseResult.discovered -> source_pages 新行。返回新增数。"""
    n_new = 0
    for d in discovered:
        freq = d.crawl_freq
        if d.category == "program_detail" and not _in_focus(uni_code, d.note):
            freq = "manual"
        _, created = registry.add_page(
            conn, university_id, d.category, d.url, title=d.title,
            crawl_freq=freq, fetch_method=d.fetch_method, note=d.note)
        n_new += created
    return n_new


def register_module_pages(conn, university_id, programs):
    """专业页模块表里带链接的模块，登记为任务；默认 manual（不自动抓详情）。"""
    freq = "monthly" if config.CRAWL_MODULE_DETAILS else "manual"
    n_new = 0
    for p in programs:
        for ref in p.modules:
            if not ref.url:
                continue
            _, created = registry.add_page(
                conn, university_id, "module_catalog", ref.url,
                title=f"{ref.code or ''} {ref.name}".strip(), crawl_freq=freq)
            n_new += created
    return n_new
