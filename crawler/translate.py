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


# ---- 校历事件名：封闭词汇表走词典（机翻会把 "Semester 1 ends" 翻成"子宫一端"）----
_CAL_PHRASES = [   # 长词组在前
    ("equal consideration", "同等考虑截止"), ("census date", "退课统计日"),
    ("examination period ends", "考试期结束"), ("examination period", "考试期"),
    ("examinations", "考试"), ("exams", "考试"), ("exam", "考试"),
    ("resit examinations", "补考"), ("resits and deferrals", "补考与延考"),
    ("resit", "补考"), ("revision", "复习周"),
    ("teaching period", "授课期"), ("teaching block", "教学段"),
    ("teaching break", "期中假"), ("teaching starts", "开课"), ("teaching ends", "授课结束"),
    ("study period", "备考期"), ("reading week", "阅读周"),
    ("welcome week", "迎新周"), ("o-week", "迎新周"), ("orientation week", "迎新周"),
    ("orientation", "迎新"), ("induction", "入学引导"), ("campus arrivals", "到校报到"),
    ("winter teaching vacation", "寒假"), ("summer teaching vacation", "暑假"),
    ("summer student vacation", "暑假"), ("spring teaching vacation", "春假"),
    ("easter vacation", "复活节假期"), ("christmas vacation", "圣诞假期"),
    ("winter vacation", "寒假"), ("summer vacation", "暑假"), ("vacation", "假期"),
    ("public holiday", "公共假期"), ("bank holiday", "公共假期"), ("holiday", "假期"),
    ("university offices re-open", "学校办公室恢复办公"),
    ("university closed", "闭校"), ("closed", "闭校"), ("closure", "闭校"),
    ("graduations", "毕业典礼"), ("graduation", "毕业典礼"),
    ("summer session", "夏季学期"), ("winter session", "冬季学期"),
    ("summer research period", "夏季研究期"),
    ("autumn semester", "秋季学期"), ("spring semester", "春季学期"),
    ("autumn term", "秋季学期"), ("spring term", "春季学期"), ("summer term", "夏季学期"),
    ("first semester", "第一学期"), ("second semester", "第二学期"),
    ("semester", "学期"), ("term dates", "学期日期"),
    ("begins", "开始"), ("commences", "开始"), ("starts", "开始"),
    ("ends", "结束"), ("finishes", "结束"), ("returns", "返校"),
    ("results from", "成绩公布："), ("results", "成绩"), ("published", "公布"),
    ("dates when the university will be", "闭校日期："), ("teaching", "授课"),
    ("flexible learning week", "弹性学习周"), ("mid-semester break", "期中假"),
    ("re-open", "恢复开放"), ("international students’", "国际学生"),
    ("international students'", "国际学生"), ("weeks", "周"),
    ("spring", "春季"), ("summer", "夏季"), ("autumn", "秋季"), ("winter", "冬季"),
    ("last day to add", "加课截止："), ("last day to drop", "退课截止："),
    ("due date for payment", "缴费截止"),
    ("new year's day", "元旦"), ("australia day", "澳大利亚日"),
    ("anzac day", "澳新军团日"), ("good friday", "耶稣受难日"),
    ("easter day", "复活节"), ("easter monday", "复活节星期一"),
    ("king's birthday", "国王诞辰日"), ("labour day", "劳动节"),
    ("reconciliation day", "和解日"), ("canberra day", "堪培拉日"),
]


def calendar_zh(name):
    """校历事件名词典翻译；词典覆盖不了的原文保留（宁缺毋滥）。"""
    out = name
    low = out.lower()
    for en, zh in _CAL_PHRASES:
        i = low.find(en)
        while i >= 0:
            out = out[:i] + zh + out[i + len(en):]
            low = out.lower()
            i = low.find(en)
    # 常见结构润色：T1/S1/学期号
    out = re.sub(r"\b[Tt](\d)([A-C]?)\b", r"T\1\2", out)
    out = re.sub(r"学期 (\d)", r"第\1学期", out)
    out = re.sub(r"\s+", " ", out).strip()
    if not re.search(r"[一-鿿]", out):
        return None
    # 残留英文超过 2 个词 → 放弃（宁保留全英文，不出中英夹杂）
    leftover = re.findall(r"[A-Za-z]{3,}", out)
    if len(leftover) > 2:
        return None
    return out
