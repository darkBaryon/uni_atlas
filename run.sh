#!/usr/bin/env bash
# uni_atlas 一键运行：
#   ./run.sh              # 抓到期页面 → 导出数据 → 打开页面（日常就用这一条）
#
# 其他子命令（按需）：
#   ./run.sh web          # 不抓取，只刷新数据并打开页面（--serve 起本地服务器）
#   ./run.sh audit        # 数据体检：逐校断言矩阵（人工验收规则的固化）
#   ./run.sh status       # 看现状：待抓任务 / 每校数据量 / 最近变更
#   ./run.sh seed <校>    # 按 crawler/config/universities/<校>.yaml 登记新学校
#   ./run.sh discover <校># 展开该校目录页 → 生成专业页任务
#   ./run.sh reparse <校> # 改完解析器离线回填快照（不联网）
#   ./run.sh crawl ...    # 任意参数透传 run.py，如 ./run.sh crawl --uni ucl --limit 50
set -euo pipefail
cd "$(dirname "$0")"

export_web() { echo "▸ 导出前端数据 ..."; python3 web/export.py; }

cmd="${1:-run}"
[ $# -gt 0 ] && shift

case "$cmd" in
  run)
    python3 crawler/run.py --due
    echo "▸ 翻译新增名称 ..."
    ( cd crawler && python3 translate_backfill.py )
    export_web
    echo "▸ 数据体检 ..."
    python3 crawler/audit.py --quiet || echo "⚠ 体检有红灯，详见上方（./run.sh audit 看全量矩阵）"
    echo "▸ 打开页面 ..."
    open web/index.html
    ;;
  audit)
    # 数据体检：逐校断言矩阵（课程量/覆盖率/垃圾名/校历时效/漏抓），红灯退出码 1
    python3 crawler/audit.py "$@"
    ;;
  web)
    exec ./web/start.sh "$@"
    ;;
  check)
    # 解析器验收：试抓 N 页（默认 15）后按字段覆盖率打分——单样本会撒谎，覆盖率不会
    [ $# -ge 1 ] || { echo "用法: ./run.sh check <校代码> [页数]" >&2; exit 2; }
    python3 crawler/run.py --uni "$1" --category program_detail --limit "${2:-15}"
    mysql study_abroad --table -e "
      SELECT COUNT(*) 专业数,
             CONCAT(SUM(pd.tuition_intl IS NOT NULL),'/',COUNT(*)) 国际学费,
             CONCAT(SUM(pd.ielts_overall IS NOT NULL OR pd.language_band IS NOT NULL),'/',COUNT(*)) 语言要求,
             CONCAT(SUM(pd.entry_req_text IS NOT NULL),'/',COUNT(*)) 学术要求,
             CONCAT(SUM(p.faculty_id IS NOT NULL),'/',COUNT(*)) 院系归属,
             (SELECT COUNT(*) FROM deadlines d JOIN programs p2 ON p2.id=d.program_id
               WHERE p2.university_id=u.id) 截止日期条数
        FROM programs p
        JOIN program_details pd ON pd.program_id=p.id
        JOIN universities u ON u.id=p.university_id
       WHERE u.code='$1' GROUP BY u.id;"
    ;;
  status)
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
    ;;
  seed)
    [ $# -ge 1 ] || { echo "用法: ./run.sh seed <校代码>" >&2; exit 2; }
    python3 crawler/run.py --seed "$1"
    ;;
  discover)
    [ $# -ge 1 ] || { echo "用法: ./run.sh discover <校代码>" >&2; exit 2; }
    python3 crawler/run.py --discover --uni "$1"
    ;;
  reparse)
    [ $# -ge 1 ] || { echo "用法: ./run.sh reparse <校代码>" >&2; exit 2; }
    python3 crawler/run.py --reparse --uni "$1"
    export_web
    ;;
  crawl)
    python3 crawler/run.py "$@"
    export_web
    ;;
  *)
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
