"""解析器包：递归导入全部子模块，子类定义即完成注册。

目录 = 国家层（parsers/uk/、以后 parsers/au/ …）：
每国一个 common.py（本国公共提取器）和 generic.py（本国通用解析器），
每校一个 <code>.py；加新校 = 在对应国家目录新建文件，无需改本文件。
"""
import importlib
import logging
import pkgutil

from parsers import base  # noqa: F401

logger = logging.getLogger(__name__)

for _mod in pkgutil.walk_packages(__path__, prefix="parsers."):
    if _mod.name == "parsers.base":
        continue
    try:
        importlib.import_module(_mod.name)
    except Exception:
        logger.exception("解析器模块 %s 导入失败（跳过）", _mod.name)

# 专属解析器全部就位后，各国通用解析器接管「只有 YAML 的学校」
from parsers.uk import generic as _uk_generic  # noqa: E402

_uk_generic.register_for_configured()
