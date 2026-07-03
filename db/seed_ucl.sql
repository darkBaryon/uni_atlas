-- =============================================================
-- UCL 种子数据（示例）
-- 数据来源：2026-07-03 官网实测（调研报告 + WebFetch 抓取）
-- 约定：官网不存在/未公开的信息，在字段中明确写出，不留空猜测
-- =============================================================
USE study_abroad;

-- 1. 院校 --------------------------------------------------------
INSERT INTO universities (code, name_en, name_zh, country, city, website, term_system, cn_student_note, extra)
VALUES ('ucl', 'University College London', '伦敦大学学院', 'UK', 'London',
        'https://www.ucl.ac.uk', '3-term',
        '中国内地学生 13,540 + 香港 1,290 (HESA 2023/24, 全英第一)',
        JSON_OBJECT('group', 'Russell Group / G5', 'ug_programs', 437, 'pgt_programs', 556,
                    'campus', 'London, Bloomsbury'));
SET @ucl := LAST_INSERT_ID();

-- 2. 学院（11 个顶层 Faculty + 演示用的下级系）---------------------
INSERT INTO faculties (university_id, parent_id, name_en, name_zh, url, level) VALUES
(@ucl, NULL, 'Faculty of Arts and Humanities',            '文学与人文学院',     'https://www.ucl.ac.uk/arts-humanities', 'faculty'),
(@ucl, NULL, 'Faculty of Brain Sciences',                 '脑科学学院',         'https://www.ucl.ac.uk/brain-sciences', 'faculty'),
(@ucl, NULL, 'The Bartlett Faculty of the Built Environment', '巴特莱特建筑学院', 'https://www.ucl.ac.uk/bartlett', 'faculty'),
(@ucl, NULL, 'Faculty of Engineering Sciences',           '工程科学学院',       'https://www.ucl.ac.uk/engineering', 'faculty'),
(@ucl, NULL, 'Faculty of Laws',                           '法学院',             'https://www.ucl.ac.uk/laws', 'faculty'),
(@ucl, NULL, 'Faculty of Life Sciences',                  '生命科学学院',       'https://www.ucl.ac.uk/life-sciences', 'faculty'),
(@ucl, NULL, 'Faculty of Mathematical and Physical Sciences', '数学与物理科学学院', 'https://www.ucl.ac.uk/mathematical-physical-sciences', 'faculty'),
(@ucl, NULL, 'Faculty of Medical Sciences',               '医学科学学院',       'https://www.ucl.ac.uk/medical-sciences', 'faculty'),
(@ucl, NULL, 'Faculty of Population Health Sciences',     '人口健康科学学院',   'https://www.ucl.ac.uk/population-health-sciences', 'faculty'),
(@ucl, NULL, 'Faculty of Social and Historical Sciences', '社会与历史科学学院', 'https://www.ucl.ac.uk/social-historical-sciences', 'faculty'),
(@ucl, NULL, 'IOE, Faculty of Education and Society',     '教育学院 (IOE)',     'https://www.ucl.ac.uk/ioe', 'faculty');

SET @fac_eng := (SELECT id FROM faculties WHERE university_id=@ucl AND name_en='Faculty of Engineering Sciences');
INSERT INTO faculties (university_id, parent_id, name_en, name_zh, url, level)
VALUES (@ucl, @fac_eng, 'UCL Computer Science', '计算机科学系', 'https://www.ucl.ac.uk/computer-science', 'department');
SET @dept_cs := LAST_INSERT_ID();

-- 3. 爬取源注册（含已失效 URL 和待采集项）--------------------------
INSERT INTO source_pages (university_id, faculty_id, category, url, title, fetch_method, crawl_freq, status, last_fetched_at, note) VALUES
(@ucl, NULL, 'term_dates',      'https://www.ucl.ac.uk/study/current-students/life-ucl/term-dates-and-closures', 'Term dates and closures', 'html', 'monthly', 'active', '2026-07-03 12:00:00', '一页含 2025/26–2027/28 多学年'),
(@ucl, NULL, 'term_dates',      'https://www.ucl.ac.uk/medical-sciences/sites/medical_sciences/files/2025-05/2526-Medical-School-Term-dates-May-25.pdf', '医学院单独校历 2025/26', 'pdf', 'monthly', 'active', NULL, '尚未解析：医学院校历为独立 PDF，日期未入 calendar_events'),
(@ucl, NULL, 'ug_admissions',   'https://www.ucl.ac.uk/prospective-students/undergraduate', 'UG admissions', 'html', 'weekly', 'active', '2026-07-03 12:00:00', NULL),
(@ucl, NULL, 'pg_admissions',   'https://www.ucl.ac.uk/prospective-students/graduate', 'PG admissions', 'html', 'weekly', 'active', '2026-07-03 12:00:00', NULL),
(@ucl, NULL, 'faculty_list',    'https://www.ucl.ac.uk/about/who-we-are/faculties-and-departments', 'Faculties and departments', 'html', 'monthly', 'active', '2026-07-03 12:00:00', NULL),
(@ucl, NULL, 'faculty_list',    'https://www.ucl.ac.uk/about-ucl/faculties', '(旧版学院列表)', 'html', 'manual', 'dead', '2026-07-03 12:00:00', '404，已被 /about/who-we-are/faculties-and-departments 取代'),
(@ucl, NULL, 'program_catalog', 'https://www.ucl.ac.uk/prospective-students/undergraduate/degrees', 'UG degrees A-Z (437门)', 'html', 'monthly', 'active', '2026-07-03 12:00:00', 'URL 模式 /undergraduate/degrees/{slug}-{year}'),
(@ucl, NULL, 'program_catalog', 'https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees', 'PGT degrees A-Z (556门)', 'html', 'monthly', 'active', '2026-07-03 12:00:00', 'URL 模式 /graduate/taught-degrees/{slug}'),
(@ucl, @dept_cs, 'program_detail', 'https://www.ucl.ac.uk/prospective-students/undergraduate/degrees/computer-science-bsc-2026', 'Computer Science BSc (2026)', 'html', 'weekly', 'active', '2026-07-03 12:00:00', NULL),
(@ucl, @dept_cs, 'program_detail', 'https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/data-science-and-machine-learning-msc', 'Data Science and Machine Learning MSc', 'html', 'weekly', 'active', '2026-07-03 12:00:00', NULL),
(@ucl, NULL, 'module_catalog',  'https://www.ucl.ac.uk/module-catalogue', 'UCL Module Catalogue', 'html', 'monthly', 'active', '2026-07-03 12:00:00', 'URL 模式 /module-catalogue/modules/{slug}-{CODE}'),
(@ucl, NULL, 'language_req',    'https://www.ucl.ac.uk/prospective-students/graduate/english-language-requirements', 'PG English language requirements', 'html', 'monthly', 'active', '2026-07-03 12:00:00', 'Level 1–5 分级制'),
(@ucl, NULL, 'china_page',      'https://www.ucl.ac.uk/prospective-students/international/china', 'Information for students from China', 'html', 'monthly', 'active', '2026-07-03 12:00:00', NULL),
(@ucl, @dept_cs, 'staff_list',  'https://www.ucl.ac.uk/computer-science/people', 'CS 系师资目录', 'html', 'monthly', 'active', NULL, '已登记、尚未采集：staff 表暂无 UCL 数据');

SET @sp_term  := (SELECT id FROM source_pages WHERE university_id=@ucl AND category='term_dates' AND fetch_method='html');
SET @sp_lang  := (SELECT id FROM source_pages WHERE university_id=@ucl AND category='language_req');
SET @sp_china := (SELECT id FROM source_pages WHERE university_id=@ucl AND category='china_page');
SET @sp_bsc   := (SELECT id FROM source_pages WHERE university_id=@ucl AND url LIKE '%computer-science-bsc-2026');
SET @sp_msc   := (SELECT id FROM source_pages WHERE university_id=@ucl AND url LIKE '%data-science-and-machine-learning-msc');
SET @sp_mod   := (SELECT id FROM source_pages WHERE university_id=@ucl AND category='module_catalog');

-- 4. 校历 2025/26（standard 校历；医学院校历见 source_pages 待解析项）
INSERT INTO calendar_events (university_id, academic_year, calendar_track, event_type, name, start_date, end_date, source_page_id, fetched_at) VALUES
(@ucl, '2025/26', 'standard', 'teaching_period', 'Term 1', '2025-09-22', '2025-12-12', @sp_term, '2026-07-03 12:00:00'),
(@ucl, '2025/26', 'standard', 'teaching_period', 'Term 2', '2026-01-12', '2026-03-27', @sp_term, '2026-07-03 12:00:00'),
(@ucl, '2025/26', 'standard', 'teaching_period', 'Term 3', '2026-04-27', '2026-06-12', @sp_term, '2026-07-03 12:00:00'),
(@ucl, '2025/26', 'standard', 'reading_week',    'Reading Week (Term 1)', '2025-11-03', '2025-11-07', @sp_term, '2026-07-03 12:00:00'),
(@ucl, '2025/26', 'standard', 'reading_week',    'Reading Week (Term 2)', '2026-02-16', '2026-02-20', @sp_term, '2026-07-03 12:00:00'),
(@ucl, '2025/26', 'standard', 'closure',         '圣诞闭校', '2025-12-23', '2026-01-05', @sp_term, '2026-07-03 12:00:00'),
(@ucl, '2025/26', 'standard', 'closure',         '复活节闭校', '2026-04-01', '2026-04-08', @sp_term, '2026-07-03 12:00:00'),
(@ucl, '2025/26', 'standard', 'exam_period',     '主考试季(官网未单列考试周,考试在Term 3内)', '2026-04-27', '2026-06-12', @sp_term, '2026-07-03 12:00:00');

-- 5. 语言分级 Level 1–5（TOEFL 为 2026-01-21 起的新版 1–6 分制）----
INSERT INTO language_bands (university_id, band_code, band_label, ielts_overall, ielts_detail, other_tests, source_page_id, fetched_at) VALUES
(@ucl, 'level-1', 'Level 1 (多数理工科)',   6.5, JSON_OBJECT('minimum_each', 6.0), JSON_OBJECT('TOEFL_new_scale', 4.5, 'TOEFL_min_each', 4.0, 'note', 'TOEFL为2026-01-21后新版1-6分制'), @sp_lang, '2026-07-03 12:00:00'),
(@ucl, 'level-2', 'Level 2',                7.0, JSON_OBJECT('minimum_each', 6.5), JSON_OBJECT('TOEFL_new_scale', 4.5, 'TOEFL_min_each', 4.5), @sp_lang, '2026-07-03 12:00:00'),
(@ucl, 'level-3', 'Level 3',                7.0, JSON_OBJECT('minimum_each', 7.0), JSON_OBJECT('TOEFL_new_scale', 5.0, 'TOEFL_min_each', 5.0), @sp_lang, '2026-07-03 12:00:00'),
(@ucl, 'level-4', 'Level 4',                7.5, JSON_OBJECT('minimum_each', 7.0), JSON_OBJECT('TOEFL_new_scale', 5.5, 'TOEFL_min_each', 5.0), @sp_lang, '2026-07-03 12:00:00'),
(@ucl, 'level-5', 'Level 5 (法律/文科高要求)', 8.0, JSON_OBJECT('minimum_each', 8.0), JSON_OBJECT('TOEFL_new_scale', 5.5, 'TOEFL_min_each', 5.5, 'TOEFL_speaking', 6.0), @sp_lang, '2026-07-03 12:00:00');

-- 6. 专业 + 年度详情 ----------------------------------------------
INSERT INTO programs (university_id, faculty_id, level, name_en, name_zh, slug, url, ucas_code, duration, subject_tags) VALUES
(@ucl, @dept_cs, 'UG',  'Computer Science BSc', '计算机科学本科', 'computer-science-bsc-2026',
 'https://www.ucl.ac.uk/prospective-students/undergraduate/degrees/computer-science-bsc-2026', 'G400', '3 years full-time',
 JSON_ARRAY('computer-science'));
SET @prog_bsc := LAST_INSERT_ID();

INSERT INTO programs (university_id, faculty_id, level, name_en, name_zh, slug, url, ucas_code, duration, subject_tags) VALUES
(@ucl, @dept_cs, 'PGT', 'Data Science and Machine Learning MSc', '数据科学与机器学习硕士', 'data-science-and-machine-learning-msc',
 'https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/data-science-and-machine-learning-msc', NULL, '1 calendar year full-time',
 JSON_ARRAY('data-science', 'machine-learning', 'computer-science'));
SET @prog_msc := LAST_INSERT_ID();

INSERT INTO program_details (program_id, entry_year, tuition_home, tuition_intl, currency,
  entry_req_text, china_req_text, language_band, ielts_overall, ielts_detail, app_open_date, scholarships, extra, source_page_id, fetched_at) VALUES
(@prog_bsc, '2026', 9790.00, 46700.00, 'GBP',
 'A-Level: A*A*A（数学或进阶数学须 A*）；IB: 40 分（3 门 HL 共 20 分，数学 7 分，偏好 Analysis and Approaches）；GCSE 英语与数学 C/4',
 '不接受高考成绩直入本科；路径：① UPC 国际预科(1年) ② 在 UCL 认可的中国大学完成两年学业且加权均分 90%（校级中国页政策）',
 'level-1', 6.5, JSON_OBJECT('minimum_each', 6.0), NULL,
 JSON_OBJECT('note', '本科奖学金信息未在该专业页公布'),
 JSON_OBJECT('admissions_test', 'TARA (Test of Academic Reasoning for Admissions)', 'campus', 'London, Bloomsbury'),
 @sp_bsc, '2026-07-03 12:00:00'),
(@prog_msc, '2026', 21500.00, 42700.00, 'GBP',
 '英国 2:1 学位（upper second-class）或同等国际学历；与 Statistical Science 系合办',
 '官网未公开统一的中国均分分档表；须在课程页 international equivalencies 下拉选择 China 查看对应要求',
 'level-2', 7.0, JSON_OBJECT('minimum_each', 6.5), '2025-10-20',
 JSON_OBJECT('note', '该专业页未列奖学金'),
 JSON_OBJECT('campus', 'London, Bloomsbury', 'partner_dept', 'UCL Statistical Science'),
 @sp_msc, '2026-07-03 12:00:00');

-- 7. 截止日期（校级 UCAS + 专业级分对象）--------------------------
INSERT INTO deadlines (university_id, program_id, entry_year, audience, deadline_type, deadline_at, note, source_page_id, fetched_at) VALUES
(@ucl, NULL,      '2026', 'all',           'equal_consideration', '2026-01-14 18:00:00', 'UCAS 本科常规截止（全校 UG 通用）', @sp_bsc, '2026-07-03 12:00:00'),
(@ucl, NULL,      '2026', 'all',           'application',         '2025-10-15 18:00:00', 'UCAS 医学类提前截止（医学院专业）', NULL, '2026-07-03 12:00:00'),
(@ucl, @prog_msc, '2026', 'international', 'application',         '2026-03-27 23:59:00', '需签证申请者截止（2025-10-20 开放）', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @prog_msc, '2026', 'home',          'application',         '2026-08-28 23:59:00', '无需签证申请者截止', @sp_msc, '2026-07-03 12:00:00');

-- 8. 课程模块（DSML MSc 的课程结构, 共 180 学分）-------------------
-- 专业页只给出模块名称与代码，未给各模块学分 → credits 为 NULL 并在 description 注明；
-- COMP0087 的完整详情来自 module-catalogue，作为"模块详情已采集"的样例
INSERT INTO modules (university_id, faculty_id, code, name_en, name_zh, credits, level, semester, description, assessment, prerequisites, url, entry_year, source_page_id, fetched_at) VALUES
(@ucl, @dept_cs, 'STAT0032', 'Introduction to Statistical Data Science', '统计数据科学导论', NULL, NULL, NULL, '仅名称/代码来自专业页；学分与详情未公布，待抓取 module-catalogue', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0081', 'Applied Machine Learning', '应用机器学习', NULL, NULL, NULL, '仅名称/代码来自专业页；学分与详情未公布，待抓取 module-catalogue', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0158', 'MSc Data Science and Machine Learning Project', '硕士毕业项目', NULL, NULL, NULL, '仅名称/代码来自专业页；学分与详情未公布，待抓取 module-catalogue', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0078', 'Supervised Learning', '监督学习', NULL, NULL, NULL, '仅名称/代码来自专业页', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0088', 'Introduction to Machine Learning', '机器学习导论', NULL, NULL, NULL, '仅名称/代码来自专业页', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0080', 'Graphical Models', '图模型', NULL, NULL, NULL, '仅名称/代码来自专业页', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0082', 'Bioinformatics', '生物信息学', NULL, NULL, NULL, '仅名称/代码来自专业页', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0084', 'Information Retrieval and Data Mining', '信息检索与数据挖掘', NULL, NULL, NULL, '仅名称/代码来自专业页', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0087', 'Statistical Natural Language Processing', '统计自然语言处理', 15, 'FHEQ Level 7', 'Term 2',
 '统计NLP基础与机器学习技术：深度学习、语言模型、机器翻译、序列标注等，理论与实践结合',
 JSON_ARRAY(JSON_OBJECT('type', 'group activity', 'weight', 100)),
 '基础概率论/线性代数/多元微积分；编程能力；至少一门机器学习课程(如COMP0078或COMP0088)',
 'https://www.ucl.ac.uk/module-catalogue/modules/statistical-natural-language-processing-COMP0087', '2026', @sp_mod, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0089', 'Reinforcement Learning', '强化学习', NULL, NULL, NULL, '仅名称/代码来自专业页', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0124', 'Multi-agent Artificial Intelligence', '多智能体人工智能', NULL, NULL, NULL, '仅名称/代码来自专业页', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0137', 'Machine Vision', '机器视觉', NULL, NULL, NULL, '仅名称/代码来自专业页', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0171', 'Bayesian Deep Learning', '贝叶斯深度学习', NULL, NULL, NULL, '仅名称/代码来自专业页', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00'),
(@ucl, @dept_cs, 'COMP0197', 'Applied Deep Learning', '应用深度学习', NULL, NULL, NULL, '仅名称/代码来自专业页', NULL, NULL, NULL, '2026', @sp_msc, '2026-07-03 12:00:00');

INSERT INTO program_modules (program_id, module_id, year_of_study, module_type, note)
SELECT @prog_msc, m.id, 1,
       CASE WHEN m.code IN ('STAT0032','COMP0081','COMP0158') THEN 'core' ELSE 'optional' END,
       CASE WHEN m.code IN ('STAT0032','COMP0081','COMP0158') THEN NULL ELSE '选修池，总学分须满 180' END
FROM modules m WHERE m.university_id=@ucl AND m.entry_year='2026';

-- 9. 中国招生政策（不存在的信息明确写出）---------------------------
INSERT INTO china_policies (university_id, entry_year, gaokao_accepted, gaokao_req, ug_pathway, pgt_gpa_rule, agent_list, china_office, source_page_id, fetched_at) VALUES
(@ucl, '2026', 0,
 '不接受高考成绩直接申请本科',
 '① UPC 国际预科（1年）；② 在 UCL 认可的中国大学完成两年学业、加权均分 90% —— 可替代 A-Level/IB',
 '【官网未公开统一分档表】UCL 不发布"中国大学均分分档"，各专业要求须在课程页 international equivalencies 选择 China 查看',
 JSON_OBJECT('exists', false, 'note', 'UCL 官网未公开授权中介名单（对比：伯明翰公布13家）'),
 '官网未公开在华办公室；相关渠道：UCL Global 中国专页 (ucl.ac.uk/global/regional-activity/ucl-and-china)、中国校友会',
 @sp_china, '2026-07-03 12:00:00');

-- 10. 学院动态示例 ------------------------------------------------
INSERT INTO faculty_info_items (university_id, faculty_id, item_type, title, summary, url, published_at, source_page_id, fetched_at) VALUES
(@ucl, @dept_cs, 'admission_notice', 'CS 本科申请者须参加 TARA 入学测试',
 '2026 entry 起 Computer Science BSc 所有申请者需参加 TARA (Test of Academic Reasoning for Admissions)',
 'https://www.ucl.ac.uk/prospective-students/undergraduate/degrees/computer-science-bsc-2026', '2025-09-01', @sp_bsc, '2026-07-03 12:00:00');
