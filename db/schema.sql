-- study_abroad 数据库结构（从真库导出，勿手改——改表后用下面命令刷新）
--   mysqldump --no-data --skip-comments --skip-add-drop-table study_abroad \
--     | sed 's/ AUTO_INCREMENT=[0-9]*//' > db/schema.sql
-- 设计说明见 db/数据库设计.md；最后刷新：2026-07-05


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `calendar_events` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `academic_year` varchar(9) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '如 2025/26',
  `calendar_track` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'standard' COMMENT '标准/医学院/教育学院等单独校历: standard | medicine | ...',
  `event_type` enum('welcome_week','teaching_period','reading_week','exam_period','resit_period','holiday','closure','graduation','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '如 "Semester 1" / "Term 2" / "圣诞闭校"',
  `start_date` date NOT NULL,
  `end_date` date DEFAULT NULL,
  `source_page_id` int unsigned DEFAULT NULL,
  `fetched_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_event` (`university_id`,`academic_year`,`calendar_track`,`event_type`,`name`),
  KEY `idx_year` (`university_id`,`academic_year`),
  KEY `fk_ce_source` (`source_page_id`),
  CONSTRAINT `fk_ce_source` FOREIGN KEY (`source_page_id`) REFERENCES `source_pages` (`id`),
  CONSTRAINT `fk_ce_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='校历事件(开学/考试/假期等)';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `change_log` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `entity_type` enum('calendar_event','program','program_detail','deadline','language_band','china_policy','china_tier','faculty','module','program_module','module_content','staff','faculty_info_item','source_page') COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_id` bigint unsigned NOT NULL,
  `change_type` enum('insert','update','delete') COLLATE utf8mb4_unicode_ci NOT NULL,
  `field_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `old_value` text COLLATE utf8mb4_unicode_ci,
  `new_value` text COLLATE utf8mb4_unicode_ci,
  `snapshot_id` bigint unsigned DEFAULT NULL COMMENT '触发本次变更的页面快照',
  `detected_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_cl` (`university_id`,`detected_at`),
  KEY `fk_cl_snap` (`snapshot_id`),
  CONSTRAINT `fk_cl_snap` FOREIGN KEY (`snapshot_id`) REFERENCES `page_snapshots` (`id`),
  CONSTRAINT `fk_cl_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='字段级变更历史(截止日期提前、学费上调等)';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `china_policies` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `entry_year` varchar(9) COLLATE utf8mb4_unicode_ci NOT NULL,
  `gaokao_accepted` tinyint(1) DEFAULT NULL COMMENT '是否接受高考直入本科',
  `gaokao_req` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '高考分数要求, 如 75–85%',
  `ug_pathway` text COLLATE utf8mb4_unicode_ci COMMENT '本科替代路径: 预科/本科读完一年直入等',
  `pgt_gpa_rule` text COLLATE utf8mb4_unicode_ci COMMENT '硕士均分规则: 按院校分档 75–87% / Band A–D 等',
  `agent_list` json DEFAULT NULL COMMENT '官方授权中介 [{name, city}]',
  `china_office` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '在华办公室/联系方式/社媒账号',
  `source_page_id` int unsigned DEFAULT NULL,
  `fetched_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_cp` (`university_id`,`entry_year`),
  KEY `fk_cp_source` (`source_page_id`),
  CONSTRAINT `fk_cp_source` FOREIGN KEY (`source_page_id`) REFERENCES `source_pages` (`id`),
  CONSTRAINT `fk_cp_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='校级中国学生招生政策';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `china_university_tiers` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL COMMENT '发布名单的外方院校',
  `entry_year` varchar(9) COLLATE utf8mb4_unicode_ci NOT NULL,
  `cn_univ_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '中国大学名称',
  `tier` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '档位: Band A / Tier 1 / 认可 ...',
  `min_score` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '该档要求均分, 如 80%',
  `note` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_page_id` int unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_tier` (`university_id`,`entry_year`,`cn_univ_name`),
  KEY `fk_ct_source` (`source_page_id`),
  CONSTRAINT `fk_ct_source` FOREIGN KEY (`source_page_id`) REFERENCES `source_pages` (`id`),
  CONSTRAINT `fk_ct_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='外方院校公布的中国大学认可/分级名单(谢菲/格拉斯哥/伯明翰等)';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `deadlines` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `program_id` int unsigned DEFAULT NULL COMMENT 'NULL = 校级统一截止(如 UCAS / 谢菲 PGT 总截止)',
  `entry_year` varchar(9) COLLATE utf8mb4_unicode_ci NOT NULL,
  `audience` enum('all','international','home') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'all',
  `deadline_type` enum('application','equal_consideration','deposit','round','language_evidence','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `round_no` tinyint unsigned DEFAULT NULL COMMENT '分轮录取的轮次',
  `deadline_at` datetime NOT NULL,
  `note` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '如 "医牙兽 UCAS" / "5个商科MSc需交押金"',
  `source_page_id` int unsigned DEFAULT NULL,
  `fetched_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_dl` (`university_id`,`entry_year`,`deadline_at`),
  KEY `idx_dl_prog` (`program_id`),
  KEY `fk_d_source` (`source_page_id`),
  CONSTRAINT `fk_d_prog` FOREIGN KEY (`program_id`) REFERENCES `programs` (`id`),
  CONSTRAINT `fk_d_source` FOREIGN KEY (`source_page_id`) REFERENCES `source_pages` (`id`),
  CONSTRAINT `fk_d_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='申请/押金/分轮截止日期';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `faculties` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `parent_id` int unsigned DEFAULT NULL COMMENT '上级学院; NULL=顶层 Faculty/College',
  `name_en` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_zh` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `url` varchar(768) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `level` enum('faculty','school','department') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'faculty',
  `description` text COLLATE utf8mb4_unicode_ci,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_faculty` (`university_id`,`name_en`),
  KEY `fk_f_parent` (`parent_id`),
  CONSTRAINT `fk_f_parent` FOREIGN KEY (`parent_id`) REFERENCES `faculties` (`id`),
  CONSTRAINT `fk_f_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学院层级(College/Faculty → School → Department)';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `faculty_info_items` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `faculty_id` int unsigned DEFAULT NULL COMMENT 'NULL=校级内容',
  `item_type` enum('news','event','research_highlight','admission_notice','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `summary` text COLLATE utf8mb4_unicode_ci,
  `url` varchar(768) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `published_at` date DEFAULT NULL,
  `source_page_id` int unsigned DEFAULT NULL,
  `fetched_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_fi` (`university_id`,`faculty_id`,`item_type`,`title`),
  KEY `idx_fi` (`university_id`,`faculty_id`,`published_at`),
  KEY `fk_fi_fac` (`faculty_id`),
  KEY `fk_fi_source` (`source_page_id`),
  CONSTRAINT `fk_fi_fac` FOREIGN KEY (`faculty_id`) REFERENCES `faculties` (`id`),
  CONSTRAINT `fk_fi_source` FOREIGN KEY (`source_page_id`) REFERENCES `source_pages` (`id`),
  CONSTRAINT `fk_fi_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学院主页下的动态/非结构化内容兜底表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `language_bands` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `band_code` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '如 B / profile-c / level-2',
  `band_label` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '如 "Band B (社科/商科/法律)"',
  `ielts_overall` decimal(2,1) NOT NULL,
  `ielts_detail` json DEFAULT NULL COMMENT '单项要求 {"writing":6.5,"listening":6.0,...}',
  `other_tests` json DEFAULT NULL COMMENT '{"TOEFL":100,"PTE":68,...}',
  `source_page_id` int unsigned DEFAULT NULL,
  `fetched_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_band` (`university_id`,`band_code`),
  KEY `fk_lb_source` (`source_page_id`),
  CONSTRAINT `fk_lb_source` FOREIGN KEY (`source_page_id`) REFERENCES `source_pages` (`id`),
  CONSTRAINT `fk_lb_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='各校语言要求分级 → 具体分数映射';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `module_contents` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `module_id` int unsigned NOT NULL,
  `entry_year` varchar(9) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '适用学年; NULL=常年适用',
  `content_type` enum('week_topic','reading','lecture_note','assignment','past_paper','exam_tips','student_review','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `seq_no` smallint unsigned DEFAULT NULL COMMENT '排序/周次',
  `title` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `body` mediumtext COLLATE utf8mb4_unicode_ci,
  `source` enum('official_public','official_gated','student','agent','manual_other') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'manual_other',
  `source_note` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `url` varchar(768) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `file_path` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `verified` tinyint(1) NOT NULL DEFAULT '0',
  `added_by` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_mc` (`module_id`,`content_type`,`seq_no`),
  CONSTRAINT `fk_mc_mod` FOREIGN KEY (`module_id`) REFERENCES `modules` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模块级课程内容(手动为主): 周安排/书单/讲义要点/备考经验';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `modules` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `faculty_id` int unsigned DEFAULT NULL COMMENT '开课学院/系',
  `code` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '模块代码, 如 COMP0087',
  `name_en` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_zh` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '中文名',
  `credits` smallint unsigned DEFAULT NULL COMMENT '学分, 如 15/20/30',
  `level` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '模块层级, 如 Level 7 / M-level',
  `semester` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '开课学期: S1 / S2 / full-year',
  `description` text COLLATE utf8mb4_unicode_ci,
  `assessment` json DEFAULT NULL COMMENT '考核方式 [{type:"exam",weight:70},{type:"coursework",weight:30}]',
  `prerequisites` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `leader` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '模块负责人',
  `extra` json DEFAULT NULL COMMENT '往年选课人数/限制条件等',
  `url` varchar(768) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `entry_year` varchar(9) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '目录年份(模块内容也按年更新)',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `source_page_id` int unsigned DEFAULT NULL,
  `fetched_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_module` (`university_id`,`code`,`entry_year`),
  KEY `idx_m_fac` (`faculty_id`),
  KEY `fk_m_source` (`source_page_id`),
  CONSTRAINT `fk_m_fac` FOREIGN KEY (`faculty_id`) REFERENCES `faculties` (`id`),
  CONSTRAINT `fk_m_source` FOREIGN KEY (`source_page_id`) REFERENCES `source_pages` (`id`),
  CONSTRAINT `fk_m_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='课程模块(一个模块可被多个专业共用)';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `page_snapshots` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `source_page_id` int unsigned NOT NULL,
  `fetched_at` datetime NOT NULL,
  `http_status` smallint DEFAULT NULL,
  `content_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_path` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '原始 html/pdf/markdown 的本地存储路径',
  `parsed_ok` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `idx_snap` (`source_page_id`,`fetched_at`),
  CONSTRAINT `fk_ps_source` FOREIGN KEY (`source_page_id`) REFERENCES `source_pages` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='抓取历史快照(仅内容变化时新增一行)';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `program_details` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `program_id` int unsigned NOT NULL,
  `entry_year` varchar(9) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '入学年份/申请季, 如 2026 或 2026/27',
  `tuition_home` decimal(10,2) DEFAULT NULL,
  `tuition_intl` decimal(10,2) DEFAULT NULL,
  `currency` char(3) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'GBP',
  `entry_req_text` text COLLATE utf8mb4_unicode_ci COMMENT '通用入学要求原文(2:1 等)',
  `china_req_text` text COLLATE utf8mb4_unicode_ci COMMENT '针对中国学历的要求(均分 80% / 认可名单等)',
  `language_band` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '学校分级代号, 关联 language_bands.band_code',
  `ielts_overall` decimal(2,1) DEFAULT NULL COMMENT '冗余存一份便于直接查询',
  `ielts_detail` json DEFAULT NULL COMMENT '{"writing":6.5,"others":6.0} 及 TOEFL/PTE 换算',
  `app_open_date` date DEFAULT NULL,
  `scholarships` json DEFAULT NULL COMMENT '[{name, amount, note}]',
  `extra` json DEFAULT NULL COMMENT '押金金额、校友折扣、分轮说明等',
  `source_page_id` int unsigned DEFAULT NULL,
  `fetched_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pd` (`program_id`,`entry_year`),
  KEY `fk_pd_source` (`source_page_id`),
  CONSTRAINT `fk_pd_prog` FOREIGN KEY (`program_id`) REFERENCES `programs` (`id`),
  CONSTRAINT `fk_pd_source` FOREIGN KEY (`source_page_id`) REFERENCES `source_pages` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='专业按申请季的详情(学费/要求/语言), 每年一行';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `program_modules` (
  `program_id` int unsigned NOT NULL,
  `module_id` int unsigned NOT NULL,
  `year_of_study` tinyint unsigned DEFAULT NULL COMMENT '本科第几学年; 硕士为 NULL 或 1',
  `module_type` enum('core','optional','elective') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'core',
  `note` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '如 "二选一" / "需先修 xx"',
  PRIMARY KEY (`program_id`,`module_id`),
  KEY `fk_pm_mod` (`module_id`),
  CONSTRAINT `fk_pm_mod` FOREIGN KEY (`module_id`) REFERENCES `modules` (`id`),
  CONSTRAINT `fk_pm_prog` FOREIGN KEY (`program_id`) REFERENCES `programs` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='专业—模块关联(必修/选修)';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `programs` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `faculty_id` int unsigned DEFAULT NULL,
  `level` enum('UG','PGT','PGR','foundation','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_en` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '如 MSc Data Science',
  `name_zh` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `slug` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '官网 URL 中的 slug/课程代码, 如 i071',
  `url` varchar(768) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ucas_code` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `duration` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '如 1 year full-time',
  `subject_tags` json DEFAULT NULL COMMENT '学科标签数组, 便于按 CS/商科/教育 检索',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_prog` (`university_id`,`level`,`name_en`),
  KEY `idx_prog_fac` (`faculty_id`),
  CONSTRAINT `fk_p_fac` FOREIGN KEY (`faculty_id`) REFERENCES `faculties` (`id`),
  CONSTRAINT `fk_p_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='专业/项目的稳定身份';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `source_pages` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `faculty_id` int unsigned DEFAULT NULL COMMENT '页面挂在哪个学院主页下; NULL=校级页面',
  `category` enum('term_dates','ug_admissions','pg_admissions','faculty_list','program_catalog','program_detail','module_catalog','staff_list','research','news','china_page','language_req','deadlines','fees','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `url` varchar(768) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fetch_method` enum('html','pdf','js_render','api','portlet_post') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'html',
  `crawl_freq` enum('daily','weekly','monthly','manual') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'weekly',
  `status` enum('active','moved','dead') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `redirect_to` varchar(768) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'status=moved 时的新地址',
  `last_fetched_at` datetime DEFAULT NULL,
  `last_changed_at` datetime DEFAULT NULL COMMENT '内容哈希最近一次变化的时间',
  `last_content_hash` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '最近快照的 sha256, 用于变更检测',
  `note` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_source` (`university_id`,`url`(500)),
  KEY `idx_due` (`crawl_freq`,`last_fetched_at`),
  KEY `idx_sp_fac` (`faculty_id`),
  CONSTRAINT `fk_sp_fac` FOREIGN KEY (`faculty_id`) REFERENCES `faculties` (`id`),
  CONSTRAINT `fk_sp_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='待监控的官方页面清单(爬取任务的唯一入口); faculty_id 外键在 faculties 建表后补加';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `university_id` int unsigned NOT NULL,
  `faculty_id` int unsigned DEFAULT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Professor / Lecturer / ...',
  `research_areas` json DEFAULT NULL COMMENT '研究方向标签数组',
  `email` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `profile_url` varchar(768) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `source_page_id` int unsigned DEFAULT NULL,
  `fetched_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_staff` (`university_id`,`name`,`faculty_id`),
  KEY `idx_st_fac` (`faculty_id`),
  KEY `fk_st_source` (`source_page_id`),
  CONSTRAINT `fk_st_fac` FOREIGN KEY (`faculty_id`) REFERENCES `faculties` (`id`),
  CONSTRAINT `fk_st_source` FOREIGN KEY (`source_page_id`) REFERENCES `source_pages` (`id`),
  CONSTRAINT `fk_st_univ` FOREIGN KEY (`university_id`) REFERENCES `universities` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学院公开师资目录';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `universities` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '内部短码, 如 ucl / manchester / hku',
  `name_en` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_zh` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `country` enum('UK','AU','HK','SG','US','CA','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `city` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `website` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `term_system` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '学制描述: 3-term / 2-semester / teaching-block',
  `cn_student_note` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '中国学生规模备注, 如 "1.1万+, HESA 2023/24 第一"',
  `extra` json DEFAULT NULL COMMENT '排名、别名、集团(罗素/八大)等杂项',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='院校主数据';
/*!40101 SET character_set_client = @saved_cs_client */;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_calendar` AS SELECT 
 1 AS `code`,
 1 AS `name_zh`,
 1 AS `academic_year`,
 1 AS `calendar_track`,
 1 AS `event_type`,
 1 AS `name`,
 1 AS `start_date`,
 1 AS `end_date`*/;
SET character_set_client = @saved_cs_client;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_program_full` AS SELECT 
 1 AS `univ`,
 1 AS `学校`,
 1 AS `level`,
 1 AS `专业`,
 1 AS `学院`,
 1 AS `entry_year`,
 1 AS `tuition_intl`,
 1 AS `currency`,
 1 AS `ielts`,
 1 AS `china_req_text`,
 1 AS `url`*/;
SET character_set_client = @saved_cs_client;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_program_modules` AS SELECT 
 1 AS `univ`,
 1 AS `专业`,
 1 AS `level`,
 1 AS `学年`,
 1 AS `类型`,
 1 AS `模块代码`,
 1 AS `模块名`,
 1 AS `学分`,
 1 AS `semester`,
 1 AS `entry_year`*/;
SET character_set_client = @saved_cs_client;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_upcoming_deadlines` AS SELECT 
 1 AS `学校`,
 1 AS `专业`,
 1 AS `entry_year`,
 1 AS `audience`,
 1 AS `deadline_type`,
 1 AS `round_no`,
 1 AS `deadline_at`,
 1 AS `note`*/;
SET character_set_client = @saved_cs_client;
/*!50001 DROP VIEW IF EXISTS `v_calendar`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_calendar` AS select `u`.`code` AS `code`,`u`.`name_zh` AS `name_zh`,`e`.`academic_year` AS `academic_year`,`e`.`calendar_track` AS `calendar_track`,`e`.`event_type` AS `event_type`,`e`.`name` AS `name`,`e`.`start_date` AS `start_date`,`e`.`end_date` AS `end_date` from (`calendar_events` `e` join `universities` `u` on((`u`.`id` = `e`.`university_id`))) order by `u`.`code`,`e`.`academic_year`,`e`.`start_date` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!50001 DROP VIEW IF EXISTS `v_program_full`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_program_full` AS select `u`.`code` AS `univ`,`u`.`name_zh` AS `学校`,`p`.`level` AS `level`,`p`.`name_en` AS `专业`,`f`.`name_en` AS `学院`,`d`.`entry_year` AS `entry_year`,`d`.`tuition_intl` AS `tuition_intl`,`d`.`currency` AS `currency`,coalesce(`d`.`ielts_overall`,`lb`.`ielts_overall`) AS `ielts`,`d`.`china_req_text` AS `china_req_text`,`p`.`url` AS `url` from ((((`programs` `p` join `universities` `u` on((`u`.`id` = `p`.`university_id`))) left join `faculties` `f` on((`f`.`id` = `p`.`faculty_id`))) left join `program_details` `d` on((`d`.`program_id` = `p`.`id`))) left join `language_bands` `lb` on(((`lb`.`university_id` = `p`.`university_id`) and (`lb`.`band_code` = `d`.`language_band`)))) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!50001 DROP VIEW IF EXISTS `v_program_modules`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_program_modules` AS select `u`.`code` AS `univ`,`p`.`name_en` AS `专业`,`p`.`level` AS `level`,`pm`.`year_of_study` AS `学年`,`pm`.`module_type` AS `类型`,`m`.`code` AS `模块代码`,`m`.`name_en` AS `模块名`,`m`.`credits` AS `学分`,`m`.`semester` AS `semester`,`m`.`entry_year` AS `entry_year` from (((`program_modules` `pm` join `programs` `p` on((`p`.`id` = `pm`.`program_id`))) join `modules` `m` on((`m`.`id` = `pm`.`module_id`))) join `universities` `u` on((`u`.`id` = `p`.`university_id`))) order by `u`.`code`,`p`.`name_en`,`pm`.`year_of_study`,`pm`.`module_type` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!50001 DROP VIEW IF EXISTS `v_upcoming_deadlines`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_upcoming_deadlines` AS select `u`.`name_zh` AS `学校`,coalesce(`p`.`name_en`,'(校级)') AS `专业`,`d`.`entry_year` AS `entry_year`,`d`.`audience` AS `audience`,`d`.`deadline_type` AS `deadline_type`,`d`.`round_no` AS `round_no`,`d`.`deadline_at` AS `deadline_at`,`d`.`note` AS `note` from ((`deadlines` `d` join `universities` `u` on((`u`.`id` = `d`.`university_id`))) left join `programs` `p` on((`p`.`id` = `d`.`program_id`))) where (`d`.`deadline_at` between now() and (now() + interval 90 day)) order by `d`.`deadline_at` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;


-- 培养计划（逐年逐学期修课序列，PDF 解析，见 crawler/plans.py）
CREATE TABLE `program_plans` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `program_id` int unsigned NOT NULL,
  `variant_label` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '主修+起始学期变体',
  `entry_year` varchar(9) COLLATE utf8mb4_unicode_ci NOT NULL,
  `plan` json NOT NULL COMMENT '结构化修课序列 years[].items[]',
  `source_url` varchar(768) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fetched_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_plan` (`program_id`,`variant_label`,`entry_year`),
  KEY `program_id` (`program_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='培养计划（逐年逐学期修课序列，PDF 解析）';
