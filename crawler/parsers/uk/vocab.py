"""英国官网措辞词汇表——国家级"翻译词典"的唯一存放处。

解析器的本质是「官网措辞 → 枚举/字段」的词典；措辞是数据不是逻辑
（ARCHITECTURE 七点六）。分层规则：
- 全英国通用的措辞 → 本文件（校历词汇/学费标签/要求标题…）
- 单校特有的措辞  → 该校解析器文件顶部（如 shef.DEADLINE_KEYWORDS）
新增措辞改这里，不碰任何逻辑代码。
"""
from config.codes import EventType

# ---- 校历事件分类（按序首中即停）----
EVENT_RULES: tuple = (
    (("welcome", "induction", "o-week", "orientation"),   # 后两者=澳洲迎新周措辞
     EventType.WELCOME_WEEK),
    # 学年整体区间（"academic year 9月至次年9月"）必须先于 orientation：
    # "academic year / Orientation" 是全年区间，不是迎新周
    (("academic year",),                      EventType.OTHER),
    (("orientation",),                        EventType.WELCOME_WEEK),
    (("reading week",),                       EventType.READING_WEEK),
    (("resit",),                              EventType.RESIT_PERIOD),
    (("exam", "assessment", "revision"),      EventType.EXAM_PERIOD),
    (("holiday",),                            EventType.HOLIDAY),
    (("vacation", "closure", "closed", "break"), EventType.CLOSURE),
    (("graduation",),                         EventType.GRADUATION),
    (("term", "semester", "teaching"),        EventType.TEACHING_PERIOD),
)
RESIT_MONTHS = ("07", "08")   # 英国主考试在春/冬，7-8 月的考试期即补考季

# ---- 学费标签（长的在前，先精确后宽泛；10 校高频值）----
FEE_INTL_LABELS = ["International & EU", "Overseas students", "International students",
                   "Overseas fee", "International fee", "Overseas", "International"]
FEE_HOME_LABELS = ["Home & RUK", "UK students", "Home students", "Home fee",
                   "Home (UK)", "Home"]

# ---- URL / 标题模式 ----
PG_URL_RE = r"/postgraduate|/masters|/taught|/pgt|-msc\b|-ma\b"
ENTRY_REQ_HEADING = (r"Entry requirements?|Academic requirements?|Qualifications|"
                     r"Academic entry qualification overview|Typical (?:A-level )?offer")
ENTRY_REQ_STOP = (r"English language|Fees|How to apply|Application and selection|"
                  r"Programme structure")
FACULTY_RE = (r"((?:Adam Smith Business School|(?:School|Faculty|College|Department)"
              r" of [A-Z][A-Za-z ,&\-]{3,70}))")

# ---- 学费语境排除词与合理区间（fee_near 用）----
FEE_EXCLUDE = ("deposit", "application fee", "scholarship", "discount",
               "bursar", "living cost", "accommodation", "per year for books")
FEE_MIN, FEE_MAX = 3500, 70000
