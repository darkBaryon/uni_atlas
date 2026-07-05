"""标识符常量层：学校代码 UniCode、页面类别 Category、校历事件 EventType。代码里引用枚举，不写裸字符串。

映射链：枚举值 = config/universities/**/<code>.yaml 的 code 字段
            = 数据库 universities.code 列。

str 混入使枚举实例可当普通字符串用（字典键/SQL 参数/配置查找无缝），
只有「写了专属解析器」的学校需要在这里登记——纯 YAML（GenericUK 接管）
的学校不出现在任何 Python 代码里，无需枚举成员。
拼错保护双保险：成员名拼错 → AttributeError（导入时）；
枚举值与 YAML 不符 → BaseParser 注册校验 TypeError（导入时）。
"""
from enum import Enum


class UniCode(str, Enum):
    # 英国
    UCL = "ucl"            # 伦敦大学学院
    GLA = "gla"            # 格拉斯哥大学
    EDI = "edi"            # 爱丁堡大学
    MAN = "man"            # 曼彻斯特大学
    BRISTOL = "bristol"    # 布里斯托大学
    LEEDS = "leeds"        # 利兹大学
    KCL = "kcl"            # 伦敦国王学院
    WARWICK = "warwick"    # 华威大学
    BHAM = "bham"          # 伯明翰大学
    SHEF = "shef"          # 谢菲尔德大学

    # 澳洲（Go8，逐校接入）
    MELB = "melb"          # 墨尔本大学
    MONASH = "monash"      # 莫纳什大学
    SYDNEY = "sydney"      # 悉尼大学
    UNSW = "unsw"          # 新南威尔士大学

    __str__ = str.__str__      # 日志/格式化输出 'bristol' 而非 'UniCode.BRISTOL'


class FetchMethod(str, Enum):
    """source_pages.fetch_method——页面的抓取方式（镜像数据库 ENUM 定义）。"""
    HTML = "html"                  # 普通 GET
    PORTLET_POST = "portlet_post"  # uPortal 门户：先 GET render.uP 预热会话再 POST 任务 URL
    JS_RENDER = "js_render"        # 需浏览器渲染（v1 不抓，报告统计）
    PDF = "pdf"                    # PDF 文档（v1 不抓，报告统计）
    API = "api"                    # JSON 接口（预留）

    __str__ = str.__str__


class Category(str, Enum):
    """页面类别——镜像数据库 source_pages.category 的 ENUM 定义。

    BaseParser 子类实现与成员值同名的方法即注册该类别的解析器。
    """
    PROGRAM_DETAIL = "program_detail"
    PROGRAM_CATALOG = "program_catalog"
    MODULE_CATALOG = "module_catalog"
    TERM_DATES = "term_dates"
    UG_ADMISSIONS = "ug_admissions"
    PG_ADMISSIONS = "pg_admissions"
    FACULTY_LIST = "faculty_list"
    LANGUAGE_REQ = "language_req"
    CHINA_PAGE = "china_page"
    DEADLINES = "deadlines"
    FEES = "fees"
    STAFF_LIST = "staff_list"
    RESEARCH = "research"
    NEWS = "news"
    OTHER = "other"

    __str__ = str.__str__


class EventType(str, Enum):
    """校历事件类型——镜像数据库 calendar_events.event_type 的 ENUM 定义。"""
    WELCOME_WEEK = "welcome_week"
    TEACHING_PERIOD = "teaching_period"
    READING_WEEK = "reading_week"
    EXAM_PERIOD = "exam_period"
    RESIT_PERIOD = "resit_period"
    HOLIDAY = "holiday"
    CLOSURE = "closure"
    GRADUATION = "graduation"
    OTHER = "other"

    __str__ = str.__str__
