"""学校代码枚举：代码里引用 UniCode.XXX，不写裸字符串。

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

    __str__ = str.__str__      # 日志/格式化输出 'bristol' 而非 'UniCode.BRISTOL'
