# uni_atlas

留学**辅导**机构的大学课程信息库：批量抓取各校官网的**课程名单+官方链接、
院系结构、校历考试期**，存入 MySQL，渲染为可读的静态页面。核心镜头是
「帮在读学生过课」——申请域字段（学费/雅思/截止）库内保留但前端收起。

**现状（2026-07-05）**：英国 10 校 + 澳洲 8 校（八大）= **18 校、8,100+ 专业、
53,000+ 课程**，课程名单带官方链接、院系归属、中文名。逐校现状与决策见
[docs/各校现状.md](docs/各校现状.md)，取数策略见 [docs/数据策略.md](docs/数据策略.md)。

## 结构

```
uni_atlas/
├── run.sh / status.sh    一键入口（run=抓取→派生→翻译→导出→体检→打开）
├── db/                   数据库层
│   ├── schema.sql            表结构（从真库导出，勿手改）
│   └── 数据库设计.md
├── crawler/              爬虫
│   ├── run.py                CLI 入口
│   ├── registry.py           source_pages 任务注册表（唯一事实）
│   ├── fetcher/              域并行 + 域内限速 + 退避 + Playwright(browser.py)
│   ├── snapshots.py          原始 HTML gzip 落盘 + sha256 变更检测
│   ├── parsers/uk|au/        按校小解析器 + 各国 common 函数库
│   ├── loader.py             upsert 入库 + change_log 字段级变更
│   ├── derive.py             派生回填（源站没有、可从已有数据推出的字段）
│   ├── translate.py          离线机翻(argos) + 校历词典翻译
│   ├── audit.py              数据体检（逐校断言矩阵）
│   └── pipeline.py           编排一次运行
├── web/                  展示层（静态页面，file:// 直开）
│   ├── export.py             MySQL → data/<地区>/<code>.js（按校懒加载）
│   └── index.html            hash 路由 SPA
└── docs/                 策略与逐校台账
```

## 数据流

```
source_pages(任务) → crawler(抓取/快照/解析) → MySQL (study_abroad)
                                              → change_log(变更播报)
   derive(派生回填) → translate(补中文) → web/export.py
                                        → web/data/*.js → web/index.html
```

## 日常用法

```bash
./run.sh                 # 抓到期 → 派生回填 → 翻译 → 导出 → 体检 → 开页面
./run.sh audit           # 数据体检：逐校断言矩阵（红灯退出码 1）
./run.sh status          # 现状报表：数据量 / 已抓构成 / 最近变更
./run.sh web             # 只导出+开页面（--serve 起本地服务器）
```

## 爬虫用法（加新学校 / 调试）

```bash
cd crawler
python3 run.py --seed <code>             # 按 config/universities/<地区>/<code>.yaml 登记
python3 run.py --discover --uni <code>   # 展开目录页 → 新任务
python3 run.py --due                     # 抓所有到期任务
python3 run.py --uni <code> --category program_detail --limit 50
python3 run.py --reparse --uni <code>    # 离线重放快照（改解析器后回填，不联网）
python3 run.py --dry-run                 # 只列任务不执行
```

**加新学校**：建 `crawler/config/universities/<地区>/<code>.yaml`（种子页 +
域限速 + 院系清单 + `expect` 体检阈值），需要结构逻辑时写
`parsers/<地区>/<code>.py` 小解析器。开工先找**行政层目录**（教务系统/handbook），
营销层只做兜底枚举——见 [docs/数据策略.md](docs/数据策略.md) 数据分层原则。

礼貌抓取：域内按 YAML 限速并发（默认 3s+抖动，实测无限流的域可调高），
域间并发，限流/挑战退避；内容哈希未变的页面跳过解析；关键字段变化写
change_log 并在报告中播报。指纹型 WAF 走 `browser.py`（Playwright 有头
浏览器，人工过一次挑战后该域复用会话）。

## 首次搭建

```bash
mysql < db/schema.sql          # 建库建表（本地 MySQL，凭据放 ~/.my.cnf）
pip install pymysql            # export 依赖
./run.sh web                   # 导出并打开页面
```

## 已收录（18 校）

**英国**：UCL、爱丁堡、格拉斯哥、曼彻斯特、利兹、伯明翰、华威、谢菲尔德、
布里斯托、KCL
**澳洲**（八大）：新南 UNSW、阿德莱德、西澳 UWA、澳国立 ANU、悉尼、
莫纳什、昆士兰 UQ、墨尔本

准数看 `./run.sh audit`；每校数据来源、缺口原因与决策见
[docs/各校现状.md](docs/各校现状.md)。下一步：港校线。
