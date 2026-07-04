"""学术名称英译中（argos-translate 离线模型 + 领域后处理规则）。

用法：from translate import to_zh; to_zh("Data Science MSc") -> "数据科学 MSc"
- 学位缩写（BSc/MSc/…）不参与翻译，原样保留在结尾；
- 完全离线（模型装在本机），~0.5s/条，结果有进程内缓存；
- 模型未安装时 to_zh 返回 None（调用方按"没有中文名"处理，不报错）。
"""
import logging
import re

logger = logging.getLogger(__name__)

_translate = None          # 惰性加载：可调用 | False(不可用) | None(未初始化)
_cache: dict[str, str] = {}

# 学位/资格缩写：截下来不翻，译完贴回
_DEGREE_RE = re.compile(
    r"\s+((?:BA|BSc|BEng|MEng|MA|MSc|MSci|MRes|MEd|MBA|MMus|MLitt|MPhil|LLB|LLM|"
    r"BAcc|BFin|BMus|BASc|BN|BDS|MBBS|PhD|EngD|PgDip|PgCert|GradDip|MPA|MPH|"
    r"MA\(SocSci\)|MSc\(MedSci\)|MVLS)(?:\s*[/&]\s*[A-Za-z()]+)*)\s*$")

# 机器翻译的领域习惯修正（保守，只放确定的）
_FIXES = [
    ("深层学习", "深度学习"),
    ("和东欧研究学校", "与东欧研究学院"),
    ("硕士学位", ""), ("学士学位", ""),
    ("耳机研究所", "耳科研究所"),
]


def _ensure_model():
    global _translate
    if _translate is not None:
        return _translate
    try:
        # argos 内部日志非常啰嗦，压到 WARNING
        for name in ("argostranslate", "argostranslate.utils", "ctranslate2", "stanza"):
            logging.getLogger(name).setLevel(logging.WARNING)
        import argostranslate.translate as tr
        # 触发一次以确认 en->zh 模型可用
        tr.translate("test", "en", "zh")
        def _do(s):
            return tr.translate(s, "en", "zh")
        _translate = _do
    except Exception as e:
        logger.warning("argos 翻译模型不可用（%s）；名称将保留英文。"
                       "安装: pip install argostranslate 并下载 en->zh 包", e)
        _translate = False  # type: ignore[assignment]  # False=模型不可用哨兵
    return _translate


def to_zh(name_en):
    """翻译学校/院系/专业/课程名；失败或模型缺失返回 None。"""
    if not name_en or not name_en.strip():
        return None
    if name_en in _cache:
        return _cache[name_en]
    fn = _ensure_model()
    if not fn:
        return None

    m = _DEGREE_RE.search(name_en)
    body = name_en[: m.start()] if m else name_en
    suffix = m.group(1) if m else ""
    if body.isupper():
        body = body.title()   # 全大写（官方目录风格）会让模型复读失控，先归一化
    try:
        zh = fn(body.strip())
    except Exception as e:
        logger.warning("翻译失败 %r: %s", name_en, e)
        return None
    if not zh or not re.search(r"[一-鿿]", zh):
        return None                      # 没译出中文就当没翻
    if len(zh) > max(60, 3 * len(body)):
        logger.warning("译文疑似复读失控，弃用 %r -> %d 字", name_en, len(zh))
        return None                      # 离线模型的退化输出（无限重复）不入库
    for a, b in _FIXES:
        zh = zh.replace(a, b)
    # 'School of X' 结尾的“学校”应为“学院”；'Division of X' 的“司”应为“部”
    if name_en.lower().startswith("school of") and zh.endswith("学校"):
        zh = zh[:-2] + "学院"
    if name_en.lower().startswith("division of"):
        zh = zh.replace("司", "部")
    zh = zh.strip(" ，。:：")
    result = (zh + (" " + suffix if suffix else "")).strip()
    _cache[name_en] = result
    return result
