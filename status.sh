#!/bin/bash
# 数据现状报表（./run.sh status 的实现）。四段：
# ① 待抓任务数 ② 每校核心数据 ③ 已抓页面构成 ④ 最近变更
set -euo pipefail
cd "$(dirname "$0")"

# 三段：① 待抓任务数 ② 每校核心数据体检（按数据策略四件套） ③ 最近变更
python3 crawler/run.py --due --dry-run 2>/dev/null | head -1 || true
echo
echo "▸ 每校核心数据（专业+归属 / 课程名单+链接 / 校历考试期 / 抓取健康）"
echo "  「未抓过」= 登记在册但一次都没抓到的页面，>0 说明有漏页要补"
mysql study_abroad --table -e "
  SELECT u.code 学校,
         (SELECT COUNT(*) FROM programs p
           WHERE p.university_id=u.id AND p.is_active=1) 专业,
         IFNULL((SELECT CONCAT(ROUND(100*SUM(p.faculty_id IS NOT NULL)/COUNT(*)),'%')
           FROM programs p WHERE p.university_id=u.id AND p.is_active=1),'—') 院系归属,
         (SELECT COUNT(*) FROM modules m
           WHERE m.university_id=u.id AND m.is_active=1) 课程,
         IFNULL((SELECT CONCAT(ROUND(100*SUM(m.url IS NOT NULL)/COUNT(*)),'%')
           FROM modules m WHERE m.university_id=u.id AND m.is_active=1),'—') 课程带链接,
         (SELECT COUNT(*) FROM calendar_events ce
           WHERE ce.university_id=u.id) 校历事件,
         (SELECT COUNT(*) FROM calendar_events ce
           WHERE ce.university_id=u.id AND ce.event_type='exam_period') 其中考试期,
         (SELECT COUNT(*) FROM source_pages sp
           WHERE sp.university_id=u.id
             AND sp.last_fetched_at IS NOT NULL) 已抓页面,
         (SELECT COUNT(*) FROM source_pages sp
           WHERE sp.university_id=u.id AND sp.status='active'
             AND sp.crawl_freq!='manual' AND sp.last_fetched_at IS NULL) 未抓过
    FROM universities u
   WHERE u.is_active=1
   ORDER BY u.country, u.code;"
echo
echo "▸ 已抓页面构成（格式 已抓/应抓，只含活跃非冻结任务）。「冻结」= manual 故意"
echo "  不抓：未来学年、课程详情链接留痕、限流挂起；「失效」= 404/搬家/垃圾清理"
mysql study_abroad --table -e "
  SELECT u.code 学校,
    CONCAT(SUM(sp.category='program_detail' AND sp.ok AND sp.last_fetched_at IS NOT NULL),
           '/', SUM(sp.category='program_detail' AND sp.ok)) 专业页,
    CONCAT(SUM(sp.category='module_catalog' AND sp.ok AND sp.last_fetched_at IS NOT NULL),
           '/', SUM(sp.category='module_catalog' AND sp.ok)) 课程名单页,
    CONCAT(SUM(sp.category='program_catalog' AND sp.ok AND sp.last_fetched_at IS NOT NULL),
           '/', SUM(sp.category='program_catalog' AND sp.ok)) 目录页,
    CONCAT(SUM(sp.category IN ('term_dates','faculty_list') AND sp.ok
               AND sp.last_fetched_at IS NOT NULL),
           '/', SUM(sp.category IN ('term_dates','faculty_list') AND sp.ok)) 校历院系,
    CONCAT(SUM(sp.category NOT IN ('program_detail','module_catalog',
                                   'program_catalog','term_dates','faculty_list')
               AND sp.ok AND sp.last_fetched_at IS NOT NULL),
           '/', SUM(sp.category NOT IN ('program_detail','module_catalog',
                                        'program_catalog','term_dates','faculty_list')
                    AND sp.ok)) 其他,
    SUM(sp.crawl_freq='manual' AND sp.status='active') 冻结,
    SUM(sp.status!='active') 失效
  FROM (SELECT s.*, (s.status='active' AND s.crawl_freq!='manual') ok
          FROM source_pages s) sp
  JOIN universities u ON u.id=sp.university_id
  GROUP BY u.code ORDER BY u.code;"
echo
echo "▸ 最近变更（同一对象反复出现同样的对调 = 解析器不稳，要查）"
mysql study_abroad --table -e "
  SELECT uu.code 学校, cl.entity_type 对象, cl.field_name 字段,
         CONCAT(LEFT(IFNULL(cl.old_value,''),21),' → ',
                LEFT(IFNULL(cl.new_value,''),21)) 变更,
         cl.detected_at 时间
    FROM change_log cl
    JOIN universities uu ON uu.id=cl.university_id
   WHERE cl.change_type='update'
   ORDER BY cl.detected_at DESC LIMIT 8;"

