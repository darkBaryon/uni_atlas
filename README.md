# uni_atlas

面向中国留学生的大学公开信息库：批量抓取各校官网的专业、截止日期、语言要求、学期日历与中国学生政策，存入 MySQL，并渲染为可读的静态页面。

## 结构

```
uni_atlas/
├── db/            数据库层
│   ├── schema.sql        建库建表（含视图）
│   ├── seed_ucl.sql      UCL 种子数据（首个样例校）
│   └── 数据库设计.md      表结构设计说明
├── scraper/       抓取脚本（规划中）
├── web/           展示层（方案 A：静态页面，无需服务器）
│   ├── export.py         从 MySQL 导出 data.js
│   ├── data.js           数据快照（由 export.py 生成）
│   └── index.html        渲染页面，双击即可打开
└── docs/          调研文档
```

## 数据流

```
爬虫 → MySQL (study_abroad) → web/export.py → web/data.js → web/index.html
```

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
