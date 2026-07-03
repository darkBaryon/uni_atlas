"""解析器框架：标准数据类 + (uni_code, category) 注册表。

解析器契约：fn(html: bytes, url: str) -> ParseResult
- 只吃本地快照内容，不碰网络；
- 字段抓不到显式置 None，并在 notes 里说明（信息不存在要写清楚）。
"""
from dataclasses import dataclass, field
from typing import Optional

PARSERS = {}   # (uni_code, category) -> fn


def register(uni_code, category):
    def deco(fn):
        PARSERS[(uni_code, category)] = fn
        return fn
    return deco


def get_parser(uni_code, category):
    return PARSERS.get((uni_code, category))


@dataclass
class DeadlineData:
    audience: str                     # all | international | home
    deadline_type: str                # application | equal_consideration | ...
    deadline_at: str                  # 'YYYY-MM-DD HH:MM:SS'
    entry_year: str
    note: Optional[str] = None


@dataclass
class ModuleRef:
    """专业页上的模块引用（只有名称/代码/链接，详情靠模块页任务补齐）。"""
    name: str
    code: Optional[str] = None
    url: Optional[str] = None
    module_type: str = "core"         # core | optional | elective


@dataclass
class ProgramData:
    name_en: str
    level: str                        # UG | PGT | PGR
    url: str
    entry_year: str
    ucas_code: Optional[str] = None
    duration: Optional[str] = None
    campus: Optional[str] = None
    faculty: Optional[str] = None
    dept: Optional[str] = None
    tuition_home: Optional[float] = None
    tuition_intl: Optional[float] = None
    currency: str = "GBP"
    fee_year_label: Optional[str] = None
    entry_req_text: Optional[str] = None
    language_band: Optional[str] = None   # UCL 式分级 'level-1'..'level-5'（无分级制的学校为 None）
    ielts_overall: Optional[float] = None  # 直接给分的学校（如格拉斯哥）
    ielts_min_each: Optional[float] = None
    app_open_date: Optional[str] = None   # 'YYYY-MM-DD'
    deadlines: list = field(default_factory=list)     # [DeadlineData]
    modules: list = field(default_factory=list)       # [ModuleRef]
    notes: list = field(default_factory=list)


@dataclass
class ModuleData:
    name_en: str
    url: str
    entry_year: str
    code: Optional[str] = None
    credits: Optional[int] = None
    level: Optional[str] = None       # 'FHEQ Level 7' 等
    semester: Optional[str] = None
    leader: Optional[str] = None
    description: Optional[str] = None
    assessment: Optional[list] = None  # [{'weight': 75, 'type': 'Exam'}]
    prerequisites: Optional[str] = None
    notes: list = field(default_factory=list)


@dataclass
class CalendarData:
    academic_year: str                # '2025/26'
    event_type: str                   # teaching_period | reading_week | ...
    name: str
    start_date: str
    end_date: Optional[str] = None
    calendar_track: str = "standard"


@dataclass
class DiscoveredPage:
    """discover 任务的产出：写回 source_pages 的新任务行。"""
    url: str
    category: str
    title: Optional[str] = None
    note: Optional[str] = None
    crawl_freq: str = "monthly"
    fetch_method: str = "html"


@dataclass
class ParseResult:
    programs: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    calendar: list = field(default_factory=list)
    deadlines: list = field(default_factory=list)     # 校级
    discovered: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def counts(self):
        parts = [(len(self.programs), "专业"), (len(self.modules), "模块"),
                 (len(self.calendar), "校历"), (len(self.deadlines), "截止"),
                 (len(self.discovered), "新任务")]
        return ", ".join(f"{n} {label}" for n, label in parts if n)
