"""解析器标准数据对象：解析器产出、装载器消费的契约层。

字段抓不到显式置 None，并在 notes/note() 里说明（信息不存在要写清楚）。
"""
from dataclasses import dataclass, field


@dataclass
class DeadlineData:
    audience: str                     # all | international | home
    deadline_type: str                # application | equal_consideration | round | ...
    deadline_at: str                  # 'YYYY-MM-DD HH:MM:SS'
    entry_year: str
    note: str | None = None
    round_no: int | None = None    # 分轮录取的轮次（deadline_type='round' 时必填）


@dataclass
class ModuleRef:
    """专业页上的课程引用（只有名称/代码/链接，详情靠课程页任务补齐）。"""
    name: str
    code: str | None = None
    url: str | None = None
    module_type: str = "core"         # core | optional | elective


@dataclass
class ProgramData:
    name_en: str
    level: str                        # UG | PGT | PGR
    url: str
    entry_year: str
    ucas_code: str | None = None
    duration: str | None = None
    campus: str | None = None
    faculty: str | None = None
    dept: str | None = None
    tuition_home: float | None = None
    tuition_intl: float | None = None
    currency: str = "GBP"
    fee_year_label: str | None = None
    entry_req_text: str | None = None
    language_band: str | None = None    # UCL 式分级；无分级制的学校为 None
    ielts_overall: float | None = None  # 直接给分的学校（如格拉斯哥）
    ielts_min_each: float | None = None
    app_open_date: str | None = None    # 'YYYY-MM-DD'
    deadlines: list = field(default_factory=list)     # [DeadlineData]
    modules: list = field(default_factory=list)       # [ModuleRef]
    notes: list = field(default_factory=list)
    backfill_only: bool = False   # 只回填已有行（归属反向索引），无匹配不建新专业


@dataclass
class ModuleData:
    name_en: str
    url: str
    entry_year: str
    code: str | None = None
    dept: str | None = None           # 开课院系（官方目录按院列课时可得）
    credits: int | None = None
    level: str | None = None       # 'FHEQ Level 7' 等
    semester: str | None = None
    leader: str | None = None
    description: str | None = None
    assessment: list | None = None  # [{'weight': 75, 'type': 'Exam'}]
    prerequisites: str | None = None
    notes: list = field(default_factory=list)


@dataclass
class CalendarData:
    academic_year: str                # '2025/26'
    event_type: str                   # teaching_period | exam_period | ...
    name: str
    start_date: str
    end_date: str | None = None
    calendar_track: str = "standard"


@dataclass
class DiscoveredPage:
    """discover 任务的产出：写回 source_pages 的新任务行。"""
    url: str
    category: str
    title: str | None = None
    note: str | None = None
    crawl_freq: str = "monthly"
    fetch_method: str = "html"


@dataclass
class ParseResult:
    programs: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    calendar: list = field(default_factory=list)
    deadlines: list = field(default_factory=list)     # 校级
    discovered: list = field(default_factory=list)
    notes: list = field(default_factory=list)   # 异常类：控制台警告（需要人看）
    infos: list = field(default_factory=list)   # 说明类：只进文件日志（页面性质等）

    def note(self, msg):
        self.notes.append(msg)

    def info(self, msg):
        """说明性备注（如"该页为参考页"）：不算异常，不上控制台。"""
        self.infos.append(msg)

    def counts(self):
        parts = [(len(self.programs), "专业"), (len(self.modules), "课程"),
                 (len(self.calendar), "校历"), (len(self.deadlines), "截止"),
                 (len(self.discovered), "新任务")]
        return ", ".join(f"{n} {label}" for n, label in parts if n)

