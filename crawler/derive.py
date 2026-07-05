#!/usr/bin/env python3
"""派生回填：源站没有、但能从已有数据推出来的字段。

用法:  python3 crawler/derive.py            # run.sh 日常流程在爬取后自动调用
幂等：只填 NULL，不覆盖已有值；阈值内推不出的保持缺（宁缺毋滥）。

规则清单（新增规则写在这里并配注释，勿散落一次性 SQL——2026-07-05 教训）：
1. 专业归属 ← 课表多数票：学位页无归属字段的学校（阿德莱德等），
   用其课表课程的院系归属投票——票数 ≥3 且过半才挂。
"""
import logging
import sys

import logging_setup
import registry

logger = logging.getLogger(__name__)

PROGRAM_FACULTY_BY_CURRICULUM = """
UPDATE programs p JOIN (
  SELECT pm.program_id, m.faculty_id, COUNT(*) v,
         SUM(COUNT(*)) OVER (PARTITION BY pm.program_id) tot,
         ROW_NUMBER() OVER (PARTITION BY pm.program_id ORDER BY COUNT(*) DESC) rn
  FROM program_modules pm
  JOIN modules m ON m.id = pm.module_id
  WHERE m.faculty_id IS NOT NULL AND m.is_active = 1
  GROUP BY pm.program_id, m.faculty_id
) t ON t.program_id = p.id AND t.rn = 1 AND t.v >= 3 AND t.v * 2 > t.tot
SET p.faculty_id = t.faculty_id
WHERE p.faculty_id IS NULL AND p.is_active = 1
"""


def main():
    logging_setup.setup()
    conn = registry.connect()
    with conn.cursor() as cur:
        cur.execute(PROGRAM_FACULTY_BY_CURRICULUM)
        n = cur.rowcount
    conn.commit()
    logger.info("派生回填：专业归属（课表多数票）+%d", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
