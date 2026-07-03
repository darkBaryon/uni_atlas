"""目录页展开：把解析出的 DiscoveredPage 与模块引用登记进 source_pages。"""
import registry


def register_discovered(conn, university_id, discovered):
    """ParseResult.discovered -> source_pages 新行。返回新增数。"""
    n_new = 0
    for d in discovered:
        _, created = registry.add_page(
            conn, university_id, d.category, d.url, title=d.title,
            crawl_freq=d.crawl_freq, fetch_method=d.fetch_method, note=d.note)
        n_new += created
    return n_new


def register_module_pages(conn, university_id, programs):
    """专业页模块表里带 module-catalogue 链接的，自动登记为模块抓取任务。"""
    n_new = 0
    for p in programs:
        for ref in p.modules:
            if not ref.url:
                continue
            _, created = registry.add_page(
                conn, university_id, "module_catalog", ref.url,
                title=f"{ref.code or ''} {ref.name}".strip(),
                crawl_freq="monthly")
            n_new += created
    return n_new
