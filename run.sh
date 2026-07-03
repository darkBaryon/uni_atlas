#!/usr/bin/env bash
# uni_atlas 一键运行：
#   ./run.sh              # 抓到期页面 → 导出数据 → 打开页面（日常就用这一条）
#
# 其他子命令（按需）：
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
    export_web
    echo "▸ 打开页面 ..."
    open web/index.html
    ;;
  status)
    python3 crawler/run.py --due --dry-run | head -1 || true
    mysql study_abroad --table -e "
      SELECT u.code 学校,
             (SELECT COUNT(*) FROM programs p
               WHERE p.university_id=u.id AND p.is_active=1) 专业,
             (SELECT COUNT(*) FROM deadlines d
               WHERE d.university_id=u.id) 截止日期,
             (SELECT COUNT(*) FROM source_pages sp
               WHERE sp.university_id=u.id AND sp.status='active'
                 AND sp.crawl_freq!='manual') 核心页面
        FROM universities u;
      SELECT entity_type 变更对象, field_name 字段, old_value 旧值, new_value 新值, detected_at 时间
        FROM change_log WHERE change_type='update'
       ORDER BY detected_at DESC LIMIT 5;"
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
