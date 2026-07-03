"""终端进度条（rich，参考 xhs-recon 的显示层约定）。

- 只在 TTY 画、走 stderr，绝不混进日志文件；
- 非 TTY（后台/重定向/cron）所有入口退化为 no-op——后台跑靠日志行看进度。
"""
from contextlib import contextmanager

from rich.console import Console
from rich.progress import (BarColumn, MofNCompleteColumn, Progress,
                           SpinnerColumn, TextColumn, TimeElapsedColumn,
                           TimeRemainingColumn)


class _NullBar:
    def describe(self, text):
        pass

    def advance(self, n=1):
        pass


class _RichBar:
    def __init__(self, progress, task_id):
        self._progress = progress
        self._task_id = task_id

    def describe(self, text):
        self._progress.update(self._task_id, description=text, refresh=True)

    def advance(self, n=1):
        self._progress.update(self._task_id, advance=n, refresh=True)


@contextmanager
def stage_bar(description, total):
    """yield 一个 describe()/advance() 句柄；非 TTY 或 total<=0 时为 no-op。"""
    console = Console(stderr=True)
    if not console.is_terminal or console.is_dumb_terminal or total <= 0:
        yield _NullBar()
        return
    prog = Progress(
        SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
        MofNCompleteColumn(), TimeElapsedColumn(), TimeRemainingColumn(),
        console=console, transient=False)
    with prog:
        task_id = prog.add_task(description, total=total)
        yield _RichBar(prog, task_id)
