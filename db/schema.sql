-- =============================================================
-- 留学院校信息库 (MySQL 8.0+)
-- 覆盖：院校 / 校历 / 学院 / 专业(按入学年份) / 截止日期 /
--       语言要求分级 / 中国学历要求 / 爬取源与快照 / 变更日志
-- =============================================================
CREATE DATABASE IF NOT EXISTS study_abroad
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE study_abroad;

-- -------------------------------------------------------------
-- 1. 院校主表
-- -------------------------------------------------------------
CREATE TABLE universities (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  code            VARCHAR(32)  NOT NULL UNIQUE COMMENT '内部短码, 如 ucl / manchester / hku',
  name_en         VARCHAR(255) NOT NULL,
  name_zh         VARCHAR(255) NOT NULL,
  country         ENUM('UK','AU','HK','SG','US','CA','other') NOT NULL,
  city            VARCHAR(128),
  website         VARCHAR(255) NOT NULL,
  term_system     VARCHAR(64)  COMMENT '学制描述: 3-term / 2-semester / teaching-block',
  cn_student_note VARCHAR(512) COMMENT '中国学生规模备注, 如 "1.1万+, HESA 2023/24 第一"',
  extra           JSON         COMMENT '排名、别名、集团(罗素/八大)等杂项',
  is_active       TINYINT(1)   NOT NULL DEFAULT 1,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '院校主数据';

-- -------------------------------------------------------------
-- 2. 爬取源注册表：每所学校要监控的官方页面
--    (term_dates / ug_admissions / pg_admissions / faculty_list /
--     program_catalog / china_page / language_req / deadlines ...)
-- -------------------------------------------------------------
CREATE TABLE source_pages (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id  INT UNSIGNED NOT NULL,
  faculty_id     INT UNSIGNED COMMENT '页面挂在哪个学院主页下; NULL=校级页面',
  category       ENUM('term_dates','ug_admissions','pg_admissions','faculty_list',
                      'program_catalog','program_detail','module_catalog',
                      'staff_list','research','news','china_page',
                      'language_req','deadlines','fees','other') NOT NULL,
  url            VARCHAR(768) NOT NULL,
  title          VARCHAR(255),
  fetch_method   ENUM('html','pdf','js_render','api') NOT NULL DEFAULT 'html'
                 COMMENT 'js_render: 如华威课程列表; pdf: 如曼大校历',
  crawl_freq     ENUM('daily','weekly','monthly','manual') NOT NULL DEFAULT 'weekly',
  status         ENUM('active','moved','dead') NOT NULL DEFAULT 'active',
  redirect_to    VARCHAR(768) COMMENT 'status=moved 时的新地址',
  last_fetched_at  DATETIME,
  last_changed_at  DATETIME COMMENT '内容哈希最近一次变化的时间',
  last_content_hash CHAR(64)  COMMENT '最近快照的 sha256, 用于变更检测',
  note           VARCHAR(512),
  UNIQUE KEY uk_source (university_id, url(500)),
  KEY idx_due (crawl_freq, last_fetched_at),
  KEY idx_sp_fac (faculty_id),
  CONSTRAINT fk_sp_univ FOREIGN KEY (university_id) REFERENCES universities(id)
) COMMENT '待监控的官方页面清单(爬取任务的唯一入口); faculty_id 外键在 faculties 建表后补加';

-- -------------------------------------------------------------
-- 3. 页面快照：原始内容留痕, 支持回溯与 diff
--    正文可存磁盘/对象存储, 表里只存路径与哈希
-- -------------------------------------------------------------
CREATE TABLE page_snapshots (
  id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  source_page_id INT UNSIGNED NOT NULL,
  fetched_at     DATETIME NOT NULL,
  http_status    SMALLINT,
  content_hash   CHAR(64) NOT NULL,
  content_path   VARCHAR(512) COMMENT '原始 html/pdf/markdown 的本地存储路径',
  parsed_ok      TINYINT(1) NOT NULL DEFAULT 0,
  KEY idx_snap (source_page_id, fetched_at),
  CONSTRAINT fk_ps_source FOREIGN KEY (source_page_id) REFERENCES source_pages(id)
) COMMENT '抓取历史快照(仅内容变化时新增一行)';

-- -------------------------------------------------------------
-- 4. 校历事件：一个学年 = 一组事件行, 天然支持多学年并存
-- -------------------------------------------------------------
CREATE TABLE calendar_events (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id  INT UNSIGNED NOT NULL,
  academic_year  VARCHAR(9)   NOT NULL COMMENT '如 2025/26',
  calendar_track VARCHAR(64)  NOT NULL DEFAULT 'standard'
                 COMMENT '标准/医学院/教育学院等单独校历: standard | medicine | ...',
  event_type     ENUM('welcome_week','teaching_period','reading_week','exam_period',
                      'resit_period','holiday','closure','graduation','other') NOT NULL,
  name           VARCHAR(255) NOT NULL COMMENT '如 "Semester 1" / "Term 2" / "圣诞闭校"',
  start_date     DATE NOT NULL,
  end_date       DATE,
  source_page_id INT UNSIGNED,
  fetched_at     DATETIME,
  UNIQUE KEY uk_event (university_id, academic_year, calendar_track, event_type, name),
  KEY idx_year (university_id, academic_year),
  CONSTRAINT fk_ce_univ FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_ce_source FOREIGN KEY (source_page_id) REFERENCES source_pages(id)
) COMMENT '校历事件(开学/考试/假期等)';

-- -------------------------------------------------------------
-- 5. 学院/学部：自引用支持 College→School→Department 多层
-- -------------------------------------------------------------
CREATE TABLE faculties (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id  INT UNSIGNED NOT NULL,
  parent_id      INT UNSIGNED COMMENT '上级学院; NULL=顶层 Faculty/College',
  name_en        VARCHAR(255) NOT NULL,
  name_zh        VARCHAR(255),
  url            VARCHAR(768),
  level          ENUM('faculty','school','department') NOT NULL DEFAULT 'faculty',
  description    TEXT,
  is_active      TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uk_faculty (university_id, name_en),
  CONSTRAINT fk_f_univ  FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_f_parent FOREIGN KEY (parent_id) REFERENCES faculties(id)
) COMMENT '学院层级(College/Faculty → School → Department)';

-- 补加 source_pages → faculties 外键(faculties 此时已存在)
ALTER TABLE source_pages
  ADD CONSTRAINT fk_sp_fac FOREIGN KEY (faculty_id) REFERENCES faculties(id);

-- -------------------------------------------------------------
-- 6. 专业(稳定身份) + 按入学年份的详情
--    programs 行一旦建立不轻易变; 每年费用/要求进 program_details
-- -------------------------------------------------------------
CREATE TABLE programs (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id  INT UNSIGNED NOT NULL,
  faculty_id     INT UNSIGNED,
  level          ENUM('UG','PGT','PGR','foundation','other') NOT NULL,
  name_en        VARCHAR(255) NOT NULL COMMENT '如 MSc Data Science',
  name_zh        VARCHAR(255),
  slug           VARCHAR(255) COMMENT '官网 URL 中的 slug/课程代码, 如 i071',
  url            VARCHAR(768),
  ucas_code      VARCHAR(16),
  duration       VARCHAR(64)  COMMENT '如 1 year full-time',
  subject_tags   JSON         COMMENT '学科标签数组, 便于按 CS/商科/教育 检索',
  is_active      TINYINT(1) NOT NULL DEFAULT 1,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_prog (university_id, level, name_en),
  KEY idx_prog_fac (faculty_id),
  CONSTRAINT fk_p_univ FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_p_fac  FOREIGN KEY (faculty_id) REFERENCES faculties(id)
) COMMENT '专业/项目的稳定身份';

CREATE TABLE program_details (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  program_id      INT UNSIGNED NOT NULL,
  entry_year      VARCHAR(9)  NOT NULL COMMENT '入学年份/申请季, 如 2026 或 2026/27',
  tuition_home    DECIMAL(10,2),
  tuition_intl    DECIMAL(10,2),
  currency        CHAR(3) NOT NULL DEFAULT 'GBP',
  entry_req_text  TEXT        COMMENT '通用入学要求原文(2:1 等)',
  china_req_text  TEXT        COMMENT '针对中国学历的要求(均分 80% / 认可名单等)',
  language_band   VARCHAR(16) COMMENT '学校分级代号, 关联 language_bands.band_code',
  ielts_overall   DECIMAL(2,1) COMMENT '冗余存一份便于直接查询',
  ielts_detail    JSON        COMMENT '{"writing":6.5,"others":6.0} 及 TOEFL/PTE 换算',
  app_open_date   DATE,
  scholarships    JSON        COMMENT '[{name, amount, note}]',
  extra           JSON        COMMENT '押金金额、校友折扣、分轮说明等',
  source_page_id  INT UNSIGNED,
  fetched_at      DATETIME,
  UNIQUE KEY uk_pd (program_id, entry_year),
  CONSTRAINT fk_pd_prog FOREIGN KEY (program_id) REFERENCES programs(id),
  CONSTRAINT fk_pd_source FOREIGN KEY (source_page_id) REFERENCES source_pages(id)
) COMMENT '专业按申请季的详情(学费/要求/语言), 每年一行';

-- -------------------------------------------------------------
-- 6b. 课程/模块 (module)：专业下的具体课程, 多对多共用
--     如利兹 module catalogue / 各校 programme structure 页
-- -------------------------------------------------------------
CREATE TABLE modules (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id  INT UNSIGNED NOT NULL,
  faculty_id     INT UNSIGNED COMMENT '开课学院/系',
  code           VARCHAR(32)  COMMENT '模块代码, 如 COMP0087',
  name_en        VARCHAR(255) NOT NULL,
  name_zh        VARCHAR(255),
  credits        SMALLINT UNSIGNED COMMENT '学分, 如 15/20/30',
  level          VARCHAR(16)  COMMENT '模块层级, 如 Level 7 / M-level',
  semester       VARCHAR(32)  COMMENT '开课学期: S1 / S2 / full-year',
  description    TEXT,
  assessment     JSON COMMENT '考核方式 [{type:"exam",weight:70},{type:"coursework",weight:30}]',
  prerequisites  VARCHAR(512),
  leader         VARCHAR(255) COMMENT '模块负责人',
  extra          JSON COMMENT '往年选课人数/限制条件等',
  url            VARCHAR(768),
  entry_year     VARCHAR(9) COMMENT '目录年份(模块内容也按年更新)',
  is_active      TINYINT(1) NOT NULL DEFAULT 1,
  source_page_id INT UNSIGNED,
  fetched_at     DATETIME,
  UNIQUE KEY uk_module (university_id, code, entry_year),
  KEY idx_m_fac (faculty_id),
  CONSTRAINT fk_m_univ FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_m_fac  FOREIGN KEY (faculty_id) REFERENCES faculties(id),
  CONSTRAINT fk_m_source FOREIGN KEY (source_page_id) REFERENCES source_pages(id)
) COMMENT '课程模块(一个模块可被多个专业共用)';

CREATE TABLE program_modules (
  program_id    INT UNSIGNED NOT NULL,
  module_id     INT UNSIGNED NOT NULL,
  year_of_study TINYINT UNSIGNED COMMENT '本科第几学年; 硕士为 NULL 或 1',
  module_type   ENUM('core','optional','elective') NOT NULL DEFAULT 'core',
  note          VARCHAR(255) COMMENT '如 "二选一" / "需先修 xx"',
  PRIMARY KEY (program_id, module_id),
  CONSTRAINT fk_pm_prog FOREIGN KEY (program_id) REFERENCES programs(id),
  CONSTRAINT fk_pm_mod  FOREIGN KEY (module_id) REFERENCES modules(id)
) COMMENT '专业—模块关联(必修/选修)';

-- -------------------------------------------------------------
-- 6b-2. 课程内容明细：模块内部的具体材料/周安排
--       公开渠道到书单为止(讲义/试卷在登录墙内), 本表以手动录入为主,
--       source + verified 字段用于区分官方信息与学生口述
-- -------------------------------------------------------------
CREATE TABLE module_contents (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  module_id     INT UNSIGNED NOT NULL,
  entry_year    VARCHAR(9) COMMENT '适用学年; NULL=常年适用',
  content_type  ENUM('week_topic',     -- 每周主题/教学安排
                     'reading',        -- 书单条目(可自动采自 Talis)
                     'lecture_note',   -- 讲义/课件要点
                     'assignment',     -- 作业/项目说明
                     'past_paper',     -- 往年考试信息
                     'exam_tips',      -- 考试重点/备考经验
                     'student_review', -- 学生评价(难度/工作量)
                     'other') NOT NULL,
  seq_no        SMALLINT UNSIGNED COMMENT '排序/周次, 如 week_topic 的第几周',
  title         VARCHAR(512) NOT NULL,
  body          MEDIUMTEXT COMMENT '正文: 主题细节/书目信息/经验内容',
  source        ENUM('official_public',  -- 官网公开(如书单)
                     'official_gated',   -- 官方但在登录墙内(转述需谨慎)
                     'student',          -- 在读/毕业学生提供
                     'agent',            -- 中介/第三方资料
                     'manual_other') NOT NULL DEFAULT 'manual_other',
  source_note   VARCHAR(512) COMMENT '来源细节: 谁提供/哪个链接/哪届学生',
  url           VARCHAR(768) COMMENT '外部链接(书目/课程页)',
  file_path     VARCHAR(512) COMMENT '本地文件(讲义PDF等)存放路径',
  verified      TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已核实',
  added_by      VARCHAR(64) COMMENT '录入人',
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_mc (module_id, content_type, seq_no),
  CONSTRAINT fk_mc_mod FOREIGN KEY (module_id) REFERENCES modules(id)
) COMMENT '模块级课程内容(手动为主): 周安排/书单/讲义要点/备考经验';

-- -------------------------------------------------------------
-- 6c. 师资(学院主页公开的 staff/people 目录)
--     用途: 科研型申请匹配导师、文书里提教授研究方向
-- -------------------------------------------------------------
CREATE TABLE staff (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id  INT UNSIGNED NOT NULL,
  faculty_id     INT UNSIGNED,
  name           VARCHAR(255) NOT NULL,
  title          VARCHAR(128) COMMENT 'Professor / Lecturer / ...',
  research_areas JSON COMMENT '研究方向标签数组',
  email          VARCHAR(255),
  profile_url    VARCHAR(768),
  is_active      TINYINT(1) NOT NULL DEFAULT 1,
  source_page_id INT UNSIGNED,
  fetched_at     DATETIME,
  UNIQUE KEY uk_staff (university_id, name, faculty_id),
  KEY idx_st_fac (faculty_id),
  CONSTRAINT fk_st_univ FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_st_fac  FOREIGN KEY (faculty_id) REFERENCES faculties(id),
  CONSTRAINT fk_st_source FOREIGN KEY (source_page_id) REFERENCES source_pages(id)
) COMMENT '学院公开师资目录';

-- -------------------------------------------------------------
-- 6d. 学院主页下的非结构化内容(新闻/研究亮点/活动/招生宣讲)
--     兜底表: 学院页面上值得保存但没有专门表的内容都进这里
-- -------------------------------------------------------------
CREATE TABLE faculty_info_items (
  id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id  INT UNSIGNED NOT NULL,
  faculty_id     INT UNSIGNED COMMENT 'NULL=校级内容',
  item_type      ENUM('news','event','research_highlight','admission_notice','other') NOT NULL,
  title          VARCHAR(512) NOT NULL,
  summary        TEXT,
  url            VARCHAR(768),
  published_at   DATE,
  source_page_id INT UNSIGNED,
  fetched_at     DATETIME,
  UNIQUE KEY uk_fi (university_id, faculty_id, item_type, title),
  KEY idx_fi (university_id, faculty_id, published_at),
  CONSTRAINT fk_fi_univ FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_fi_fac  FOREIGN KEY (faculty_id) REFERENCES faculties(id),
  CONSTRAINT fk_fi_source FOREIGN KEY (source_page_id) REFERENCES source_pages(id)
) COMMENT '学院主页下的动态/非结构化内容兜底表';

-- -------------------------------------------------------------
-- 7. 截止日期：支持校级与专业级、分对象、分轮次
-- -------------------------------------------------------------
CREATE TABLE deadlines (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id  INT UNSIGNED NOT NULL,
  program_id     INT UNSIGNED COMMENT 'NULL = 校级统一截止(如 UCAS / 谢菲 PGT 总截止)',
  entry_year     VARCHAR(9) NOT NULL,
  audience       ENUM('all','international','home') NOT NULL DEFAULT 'all',
  deadline_type  ENUM('application','equal_consideration','deposit','round',
                      'language_evidence','other') NOT NULL,
  round_no       TINYINT UNSIGNED COMMENT '分轮录取的轮次',
  deadline_at    DATETIME NOT NULL,
  note           VARCHAR(512) COMMENT '如 "医牙兽 UCAS" / "5个商科MSc需交押金"',
  source_page_id INT UNSIGNED,
  fetched_at     DATETIME,
  KEY idx_dl (university_id, entry_year, deadline_at),
  KEY idx_dl_prog (program_id),
  CONSTRAINT fk_d_univ FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_d_prog FOREIGN KEY (program_id) REFERENCES programs(id),
  CONSTRAINT fk_d_source FOREIGN KEY (source_page_id) REFERENCES source_pages(id)
) COMMENT '申请/押金/分轮截止日期';

-- -------------------------------------------------------------
-- 8. 语言要求分级表：KCL Band A–E / Bristol Profile A–H / UCL Level 1–5
-- -------------------------------------------------------------
CREATE TABLE language_bands (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id  INT UNSIGNED NOT NULL,
  band_code      VARCHAR(16) NOT NULL COMMENT '如 B / profile-c / level-2',
  band_label     VARCHAR(128) COMMENT '如 "Band B (社科/商科/法律)"',
  ielts_overall  DECIMAL(2,1) NOT NULL,
  ielts_detail   JSON COMMENT '单项要求 {"writing":6.5,"listening":6.0,...}',
  other_tests    JSON COMMENT '{"TOEFL":100,"PTE":68,...}',
  source_page_id INT UNSIGNED,
  fetched_at     DATETIME,
  UNIQUE KEY uk_band (university_id, band_code),
  CONSTRAINT fk_lb_univ FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_lb_source FOREIGN KEY (source_page_id) REFERENCES source_pages(id)
) COMMENT '各校语言要求分级 → 具体分数映射';

-- -------------------------------------------------------------
-- 9. 中国学历政策(校级) + 中国大学认可/分级名单
-- -------------------------------------------------------------
CREATE TABLE china_policies (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id   INT UNSIGNED NOT NULL,
  entry_year      VARCHAR(9) NOT NULL,
  gaokao_accepted TINYINT(1) COMMENT '是否接受高考直入本科',
  gaokao_req      VARCHAR(512) COMMENT '高考分数要求, 如 75–85%',
  ug_pathway      TEXT COMMENT '本科替代路径: 预科/本科读完一年直入等',
  pgt_gpa_rule    TEXT COMMENT '硕士均分规则: 按院校分档 75–87% / Band A–D 等',
  agent_list      JSON COMMENT '官方授权中介 [{name, city}]',
  china_office    VARCHAR(512) COMMENT '在华办公室/联系方式/社媒账号',
  source_page_id  INT UNSIGNED,
  fetched_at      DATETIME,
  UNIQUE KEY uk_cp (university_id, entry_year),
  CONSTRAINT fk_cp_univ FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_cp_source FOREIGN KEY (source_page_id) REFERENCES source_pages(id)
) COMMENT '校级中国学生招生政策';

CREATE TABLE china_university_tiers (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id  INT UNSIGNED NOT NULL COMMENT '发布名单的外方院校',
  entry_year     VARCHAR(9) NOT NULL,
  cn_univ_name   VARCHAR(255) NOT NULL COMMENT '中国大学名称',
  tier           VARCHAR(64)  COMMENT '档位: Band A / Tier 1 / 认可 ...',
  min_score      VARCHAR(64)  COMMENT '该档要求均分, 如 80%',
  note           VARCHAR(512),
  source_page_id INT UNSIGNED,
  UNIQUE KEY uk_tier (university_id, entry_year, cn_univ_name),
  CONSTRAINT fk_ct_univ FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_ct_source FOREIGN KEY (source_page_id) REFERENCES source_pages(id)
) COMMENT '外方院校公布的中国大学认可/分级名单(谢菲/格拉斯哥/伯明翰等)';

-- -------------------------------------------------------------
-- 10. 变更日志：结构化数据每次更新留痕, 供"最新动态"推送
-- -------------------------------------------------------------
CREATE TABLE change_log (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  university_id INT UNSIGNED NOT NULL,
  entity_type   ENUM('calendar_event','program','program_detail','deadline',
                     'language_band','china_policy','china_tier','faculty',
                     'module','program_module','module_content','staff',
                     'faculty_info_item','source_page') NOT NULL,
  entity_id     BIGINT UNSIGNED NOT NULL,
  change_type   ENUM('insert','update','delete') NOT NULL,
  field_name    VARCHAR(64),
  old_value     TEXT,
  new_value     TEXT,
  snapshot_id   BIGINT UNSIGNED COMMENT '触发本次变更的页面快照',
  detected_at   DATETIME NOT NULL,
  KEY idx_cl (university_id, detected_at),
  CONSTRAINT fk_cl_univ FOREIGN KEY (university_id) REFERENCES universities(id),
  CONSTRAINT fk_cl_snap FOREIGN KEY (snapshot_id) REFERENCES page_snapshots(id)
) COMMENT '字段级变更历史(截止日期提前、学费上调等)';

-- =============================================================
-- 常用查询视图
-- =============================================================

-- 某校某学年校历一览
CREATE OR REPLACE VIEW v_calendar AS
SELECT u.code, u.name_zh, e.academic_year, e.calendar_track,
       e.event_type, e.name, e.start_date, e.end_date
FROM calendar_events e JOIN universities u ON u.id = e.university_id
ORDER BY u.code, e.academic_year, e.start_date;

-- 专业详情大宽表(咨询时直接查)
CREATE OR REPLACE VIEW v_program_full AS
SELECT u.code AS univ, u.name_zh AS 学校, p.level, p.name_en AS 专业,
       f.name_en AS 学院, d.entry_year, d.tuition_intl, d.currency,
       COALESCE(d.ielts_overall, lb.ielts_overall) AS ielts,
       d.china_req_text, p.url
FROM programs p
JOIN universities u ON u.id = p.university_id
LEFT JOIN faculties f ON f.id = p.faculty_id
LEFT JOIN program_details d ON d.program_id = p.id
LEFT JOIN language_bands lb ON lb.university_id = p.university_id
       AND lb.band_code = d.language_band;

-- 某专业的课程设置(咨询时展示"这个专业学什么")
CREATE OR REPLACE VIEW v_program_modules AS
SELECT u.code AS univ, p.name_en AS 专业, p.level,
       pm.year_of_study AS 学年, pm.module_type AS 类型,
       m.code AS 模块代码, m.name_en AS 模块名, m.credits AS 学分,
       m.semester, m.entry_year
FROM program_modules pm
JOIN programs p ON p.id = pm.program_id
JOIN modules m  ON m.id = pm.module_id
JOIN universities u ON u.id = p.university_id
ORDER BY u.code, p.name_en, pm.year_of_study, pm.module_type;

-- 未来 90 天内的截止日期(提醒用)
CREATE OR REPLACE VIEW v_upcoming_deadlines AS
SELECT u.name_zh AS 学校, COALESCE(p.name_en, '(校级)') AS 专业,
       d.entry_year, d.audience, d.deadline_type, d.round_no,
       d.deadline_at, d.note
FROM deadlines d
JOIN universities u ON u.id = d.university_id
LEFT JOIN programs p ON p.id = d.program_id
WHERE d.deadline_at BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL 90 DAY)
ORDER BY d.deadline_at;
