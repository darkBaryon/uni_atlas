"""解析器包：自动导入本目录全部模块，子类定义即完成注册。

加一所新学校 = 新建 parsers/<code>.py（BaseParser 子类），无需改本文件。
"""
import importlib
import logging
import pkgutil

from parsers import base  # noqa: F401

logger = logging.getLogger(__name__)

for _mod in pkgutil.iter_modules(__path__):
    if _mod.name == "base":
        continue
    try:
        importlib.import_module(f"parsers.{_mod.name}")
    except Exception:
        logger.exception("解析器模块 parsers/%s.py 导入失败（跳过）", _mod.name)
