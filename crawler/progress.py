"""终端进度显示（rich）：只在 TTY 画、走 stderr，绝不混进日志文件。

层级（参考 xhs-recon 的父子进度约定）：
  总进度  ━━━━  123/1140
  伦敦大学学院    ━━━━  80/769   ← 每校一条（中文名），域间并行各走各的
  └ 当前: [专业页] 文学与人文 · Ancient History BA   ← 孙级信息在描述行滚动

非 TTY（后台/重定向/cron）所有入口退化为 no-op——后台跑靠日志行看进度。
"""
from contextlib import contextmanager

from rich.console import Console
from rich.progress import (BarColumn, MofNCompleteColumn, Progress,
                           SpinnerColumn, TextColumn, TimeElapsedColumn,
                           TimeRemainingColumn)

# 全局共享 Console：日志与进度条都经它输出，rich 才能协调
# 「收起活动条 → 打印日志 → 重画」，否则日志行会把旧条形顶成僵尸留在滚动区
console = Console(stderr=True)

CATEGORY_ZH = {
    "program_detail": "专业页", "program_catalog": "专业目录",
    "module_catalog": "模块页", "term_dates": "校历",
    "ug_admissions": "本科招生", "pg_admissions": "硕士招生",
    "language_req": "语言要求", "china_page": "中国专页",
    "faculty_list": "学院列表", "staff_list": "师资",
    "deadlines": "截止日期", "fees": "学费", "news": "新闻",
    "research": "科研", "other": "其他",
}


class _NullBars:
    def advance(self, uni_code):
        pass

    def describe(self, uni_code, text):
        pass


class _RichBars:
    def __init__(self, progress, overall_id, school_ids, school_labels):
        self._p = progress
        self._overall = overall_id
        self._schools = school_ids          # uni_code -> task_id
        self._labels = school_labels        # uni_code -> 中文名

    def advance(self, uni_code):
        self._p.update(self._overall, advance=1, refresh=True)
        tid = self._schools.get(uni_code)
        if tid is not None and tid != self._overall:  # 单校时学校条即总条，避免加两次
            self._p.update(tid, advance=1, refresh=True)

    def describe(self, uni_code, text):
        tid = self._schools.get(uni_code)
        if tid is not None:
            label = self._labels.get(uni_code, uni_code)
            self._p.update(tid, description=f"{label} · {text}", refresh=True)


def page_desc(task):
    """孙级描述：学院 · 专业名（专业页不再带类别字样；其他类别保留标签）。"""
    parts = []
    if task.get("category") != "program_detail":
        parts.append(f"[{CATEGORY_ZH.get(task.get('category'), task.get('category', ''))}]")
    note = task.get("note") or ""
    if "|" in note:                       # UCL 式 'Faculty | Dept' 取院系
        parts.append(note.split("|")[-1].strip()[:24] + " ·")
    title = task.get("title")
    parts.append((title or task.get("url", "").rstrip("/").rsplit("/", 1)[-1])[:48])
    return " ".join(parts)


@contextmanager
def crawl_bars(schools, mode="抓取"):
    """schools: [(uni_code, 中文名, 任务数), ...]；yield advance()/describe() 句柄。

    单校时不画总进度条（避免两条一样的）；非 TTY 时 yield no-op。
    """
    total = sum(n for _, _, n in schools)
    if not console.is_terminal or console.is_dumb_terminal or total <= 0:
        yield _NullBars()
        return
    prog = Progress(
        SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
        MofNCompleteColumn(), TimeElapsedColumn(), TimeRemainingColumn(),
        console=console, transient=False)
    with prog:
        overall_id = prog.add_task(f"{mode}总进度", total=total)
        school_ids, school_labels = {}, {}
        if len(schools) > 1:
            for code, label, n in schools:
                school_ids[code] = prog.add_task(label or code, total=n)
                school_labels[code] = label or code
        else:  # 单校：学校条即总条，描述行直接挂总条上
            code, label, _ = schools[0]
            school_ids[code] = overall_id
            school_labels[code] = label or code
            prog.update(overall_id, description=label or code)
        yield _RichBars(prog, overall_id, school_ids, school_labels)
