# uni_atlas 爬虫架构

> 设计日期：2026-07。基于 UCL 试点的实测经验（Cloudflare 限速、选择器、公开信息边界）。

## 一、并行模型：域名级并行 + 域内限速

```
                     ┌──────────────────────────────────────┐
                     │  asyncio 事件循环 (单进程)              │
   source_pages ──▶  │                                      │
   (任务注册表)       │  ucl.ac.uk 队列 ──▶ [3s间隔] 串行抓取  │
                     │  gla.ac.uk 队列 ──▶ [3s间隔] 串行抓取  │ ──▶ 快照/解析/入库
                     │  shef.ac.uk 队列 ─▶ [3s间隔] 串行抓取  │
                     │  ... (最多 MAX_DOMAINS=10 个域并发)    │
                     └──────────────────────────────────────┘
```

- **域内**：每个域名一条 FIFO 队列，请求间隔 = `min_interval + 随机抖动(0~1s)`（默认 3s，可按域覆盖）。触发反爬时该域指数退避（30s/60s/120s），不影响其他域。
- **域间**：完全并发。10 所学校同时爬，总吞吐 ≈ 10 × (1页/3s) ≈ 12,000 页/小时，够用。
- **为什么单进程 asyncio 而不是多进程/分布式**：瓶颈是礼貌限速而非 CPU；单进程足够打满所有域的限速配额，还避免了跨进程协调限速的复杂度。数据量再大也是"每域慢"，加进程无济于事。

**规模估算**：UCL 全量（1076 专业 + ~5000 模块 + 书单）≈ 7000 页 ≈ 单域 6 小时。
英国 10 校全量约 5–7 万页，跨域并行一个通宵可完成；增量更新（哈希未变跳过解析）快得多。

## 二、任务驱动：source_pages 是唯一事实

一切待抓 URL 都先登记进 `source_pages`，爬虫只从表里取任务。好处：

- **断点续爬天然支持**：任务状态就是 `last_fetched_at`，进程挂了重启接着跑；
- **增量调度**：按 `crawl_freq + last_fetched_at` 挑到期任务，申请季可把 deadlines 类调成 daily；
- **失败留痕**：Cloudflare 挑战 3 次失败 → note 标记，下轮重试；404 → status='dead'；301 → 记 redirect_to。

两类任务：

| 类型 | 干什么 | 例子 |
|---|---|---|
| **discover**（发现） | 抓目录页 → 解析出子页 URL → **写入新的 source_pages 行** | UCL 目录页 → 生成 1076 个 program_detail 任务 |
| **fetch**（采集） | 抓详情页 → 快照 → 解析 → 入库 | 专业页、模块页、校历页 |

discover 让爬虫自我扩张：先手动登记每校几个目录页，之后任务表自动长出全部详情页。

## 三、流水线：抓取与解析解耦

```
调度器 ──▶ 抓取器 ──▶ 快照层 ──哈希未变──▶ 仅更新 last_fetched_at（不解析）
                        │
                        └─哈希变了──▶ 落盘 snapshots/{uni}/{category}/
                                      + page_snapshots 登记
                                          │
                                      解析器 ──▶ 标准数据对象 ──▶ 装载器 upsert
                                                                    │
                                                              新旧值不同 → change_log
```

**关键决策：解析器只吃本地快照文件，不直接吃网络响应。**
- 解析器出 bug → `--reparse` 离线重放全部快照，**不用重新抓取**（UCL 试点吃过这个亏：学费正则错了被迫重爬 39 页）；
- 新增字段 → 同样离线重放历史快照即可回填。

## 四、解析器组织：按校注册，输出标准对象

```
parsers/
  models.py      # 标准数据类: ProgramData / ModuleData / CalendarData / DeadlineData
  page.py        # 页面提取工具: Page 类 + parse_date/money/norm_ws
  base.py        # BaseParser 基类与注册表（子类定义即注册）
  uk/            # 国家层: common.py(公共提取器) + generic.py(通用解析器) + 每校一个
  ucl.py         # register('ucl', 'program_detail', parse_ucl_program) ...
  sheffield.py   # 每校一个文件，注册表 (uni_code, category) -> 函数
```

- 解析器输出**标准数据类**（和 schema 字段对齐），装载器 (`loader.py`) 统一负责 upsert 和 change_log —— 加一所新学校只写解析函数，入库逻辑零重复；
- 字段抓不到时显式置 None + `notes` 说明（沿用"信息不存在要写清楚"原则）。

## 五、目录结构

```
crawler/
  ARCHITECTURE.md   # 本文档
  config/           # 全局默认 (__init__.py) + 每校一个 YAML
    universities/
      ucl.yaml      # 域名限速/申请季/抓取范围/入口页种子；加新校=新建一个 YAML
  registry.py       # source_pages 读任务/写状态（唯一接触任务表的模块）
  fetcher.py        # 域名队列 + 限速 + 退避重试 + Cloudflare/404/301 识别
  snapshots.py      # 落盘 + sha256 变更检测 + page_snapshots 登记
  parsers/          # 见上
  loader.py         # 标准对象 -> MySQL upsert + change_log
  pipeline.py       # 编排一次运行: 取任务→抓→存→解析→装载→报告
  discover.py       # 目录页展开逻辑（写新 source_pages 行）
  run.py            # CLI 入口
```

## 六、CLI 用法（run.py）

```bash
python3 run.py --due                     # 抓所有到期任务（日常 cron 用）
python3 run.py --uni ucl                 # 只跑某校
python3 run.py --uni ucl --category program_detail --limit 50   # 定向+限量
python3 run.py --discover --uni ucl      # 只跑发现任务（展开目录）
python3 run.py --reparse --uni ucl       # 离线重放快照（不联网）
python3 run.py --dry-run                 # 只列出将执行的任务
```

结束输出报告：抓取数/变更数/失败数/新发现任务数 + change_log 摘要（学费变了、截止提前了）。

## 七、失败与反爬策略

| 情况 | 识别 | 处理 |
|---|---|---|
| Cloudflare 挑战 | 响应含 "Just a moment" | 该域退避 30s→60s→120s，3 次失败标 note 留待下轮；**不影响其他域** |
| 404 | http_status | source_pages.status='dead'，报告里列出 |
| 301/302 跨页 | Location 头 | status='moved' + redirect_to，下轮抓新地址 |
| JS 渲染页 | fetch_method='js_render' | v1 跳过并计数报告（如华威课程列表、UCL Profiles），后续接 Playwright 作为独立 fetcher |
| PDF | fetch_method='pdf' | 只落盘快照登记，解析暂缓（如曼大校历） |

## 七点五、设计决策：按技术分层，不按学校分域

`config/universities/*.yaml` + `parsers/*.py` 按技术分层，而非
`universities/<校>/{config,parser}` 业务域结构。判断依据是**域间差异度**：
业务域架构的收益在「域文件多、域间共性小」时才兑现；本项目各校抓取流程
95% 相同，按技术分层才能把公共层（BaseParser/GenericUK/uk_common）做到
最大，学校个性压到最薄——理想态是新校只有一个 YAML、零 Python。
每校资产靠命名约定（`<code>.yaml` / `<code>.py`）保持可寻。
**切换信号**：若将来每校长出多个伴生文件（测试样本/单测/文档），再迁业务域。

## 八、边界（v1 明确不做）

- **不做全站镜像**——核心数据 = 校级关键页（校历/截止/语言/中国政策）+ 关注院系的专业页
  （`config.FOCUS_DEPTS`）。模块详情页默认不抓（`CRAWL_MODULE_DETAILS=False`，专业页自带
  模块名单已够用）；范围外页面照常登记进 source_pages 但 `crawl_freq='manual'` 留档，
  需要时定向抓，`--due` 永不选中；
- 不做分布式/代理池——礼貌限速下单机足够，也符合合规姿态；
- 不做 JS 渲染（登记跳过，v2 用 Playwright 单独跑小批量）；
- 不绕过登录墙（Moodle 讲义等本来就是 module_contents 手动录入的范围）。
```

## 七点六、解析器编码规范：措辞是数据，不是逻辑

解析器本质是「官网措辞 → schema 字段」的翻译词典，源站措辞（"applications
close"、"Home & RUK"）无法从代码中消除——它们是解析器承载的数据本身。
规范是控制它们的**存放形式**：

1. 措辞一律提升为模块顶部命名常量（正则 `XXX_RE` / 词典表 `XXX_KEYWORDS`），
   注明实测日期；函数体内不出现内联的源站措辞字符串；
2. 语义映射（措辞 → 类型/受众）写成表驱动（参见 shef.DEADLINE_KEYWORDS），
   官网改词时只改表、不读逻辑；
3. 规则规整的学校优先走 GenericUK + YAML（措辞彻底出代码）；
   写专属解析器 = 承认该校规则不规整，措辞表就留在该校文件顶部。
