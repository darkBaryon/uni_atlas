"""澳洲大学解析器包（国家层）。

英国十校的教训（见 memory: library-over-framework-parsers）：不建 generic.py，
每校直接写小解析器；公共提取逻辑等第二所学校出现重复时再上提 common.py
（被 ≥2 校调用才上提，避免为单校抽象）。
"""
