# uni_atlas

面向中国留学生的大学公开信息库：批量抓取各校官网的专业、截止日期、语言要求、学期日历与中国学生政策，存入 MySQL，并渲染为可读的静态页面。

## 结构

```
uni_atlas/
├── db/            数据库层
│   ├── schema.sql        建库建表（含视图）
│   ├── seed_ucl.sql      UCL 种子数据（首个样例校）
│   └── 数据库设计.md      表结构设计说明
├── crawler/       爬虫（架构见 crawler/ARCHITECTURE.md）
│   ├── run.py            CLI 入口
│   ├── registry.py       source_pages 任务注册表（唯一事实）
│   ├── fetcher.py        域名级并行 + 域内限速 + Cloudflare 退避
│   ├── snapshots.py      原始 HTML 落盘 + sha256 变更检测
│   ├── parsers/          按校注册的解析器（输出标准数据对象）
│   ├── loader.py         upsert 入库 + change_log 字段级变更
│   ├── discover.py       目录页自动展开出新任务
│   └── pipeline.py       编排一次运行
├── web/           展示层（静态页面，无需服务器）
│   ├── export.py         从 MySQL 导出 data.js
│   └── index.html        四级下钻 SPA（./web/start.sh 启动）
└── docs/          调研文档
```

## 数据流

```
source_pages(任务) → crawler(抓取/快照/解析) → MySQL (study_abroad)
                                                → change_log(变更播报)
                     → web/export.py → web/data.js → web/index.html
```

## 爬虫用法

```bash
cd crawler                                # 加新学校: 建 config/universities/<code>.yaml 后 --seed <code>
python3 run.py --due                     # 抓所有到期任务（日常）
python3 run.py --uni ucl --category program_detail --limit 50
python3 run.py --discover --uni ucl      # 展开目录页 → 新任务
python3 run.py --reparse --uni ucl       # 离线重放快照（改解析器后回填，不联网）
python3 run.py --dry-run                 # 只列任务不执行
```

礼貌抓取：域内 3s+抖动串行、域间并发、Cloudflare 指数退避；
内容哈希未变的页面跳过解析；学费/截止日期等关键字段变化会写入 change_log 并在报告中播报。

## 使用

```bash
# 1. 建库（本地 MySQL，凭据放 ~/.my.cnf）
mysql < db/schema.sql
mysql study_abroad < db/seed_ucl.sql

# 2. 导出数据（依赖: pip install pymysql）
python3 web/export.py

# 3. 查看页面
open web/index.html
```

数据更新后重跑第 2 步并刷新页面即可。库中新增大学会自动出现在页面顶部的切换栏中。

## 已收录

| 大学 | 专业 | 数据抓取日 |
|---|---|---|
| University College London（伦敦大学学院） | CS 本科、数据科学与机器学习硕士 | 2026-07-03 |
