"""日志装配（参考 xhs-recon 的双通道方案）。

- 控制台给人看：时分秒 + 消息，WARNING 以上带 ⚠/✖ 标记和出处；
- 文件给复盘用：全量字段，逐行带级别/模块/行号，写入 logs/crawl-<时间戳>.log。

只有 run.py 入口调用 setup()；其余模块一律 logging.getLogger(__name__)。
"""
import logging
import os
from datetime import datetime

import config
import progress

CONSOLE_DATEFMT = "%H:%M:%S"
FILE_FORMAT = ("%(asctime)s %(levelname)-7s %(name)s"
               " %(filename)s:%(lineno)d %(message)s")
LOG_DIR = os.path.join(config.ROOT, "logs")


class ConsoleFormatter(logging.Formatter):
    """成功路径保持叙事干净；警告以上带醒目标记与出处。"""

    def __init__(self):
        super().__init__("%(asctime)s %(mark)s%(message)s", datefmt=CONSOLE_DATEFMT)

    def format(self, record):
        if record.levelno >= logging.ERROR:
            record.mark = "✖ "
        elif record.levelno >= logging.WARNING:
            record.mark = "⚠ "
        else:
            record.mark = ""
        line = super().format(record)
        if record.levelno >= logging.WARNING:
            line += f" · {record.filename}:{record.lineno}"
        return line


class RichConsoleHandler(logging.Handler):
    """控制台日志经 rich Console 输出：进度条活动时自动“收起→打印→重画”，
    避免日志行把旧进度条顶成僵尸留在滚动区。"""

    def emit(self, record):
        try:
            progress.console.print(self.format(record),
                                   highlight=False, markup=False)
        except Exception:
            self.handleError(record)


def setup(verbose=False):
    """配置根 logger；返回本次运行的文件日志路径（不可用时 None）。"""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    console = RichConsoleHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(ConsoleFormatter())
    root.addHandler(console)

    log_path = None
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        log_path = os.path.join(LOG_DIR, f"crawl-{stamp}.log")
        fh = logging.FileHandler(log_path, encoding="utf-8")
    except OSError as e:
        log_path = None
        logging.getLogger(__name__).warning("文件日志不可用：%s（仅控制台输出）", e)
    else:
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(FILE_FORMAT))
        root.addHandler(fh)

    # 头行预告全量日志位置——报错时知道去哪翻
    if log_path:
        logging.getLogger(__name__).info("▶ 开始运行 · 全量日志 %s", log_path)
    return log_path
