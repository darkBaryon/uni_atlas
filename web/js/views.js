/* ============================================================
   views.js — 四个视图的渲染函数（纯函数：数据 → HTML 字符串）
   挂载到 window.VIEWS；路由与状态在 app.js
   视图: overview / university / program / module
   ============================================================ */
(function () {
  "use strict";
  var UI = window.UI, esc = UI.esc;
  var VIEWS = {};

  /* ---------------- 概览页 ---------------- */
  VIEWS.overview = function (data) {
    var h = '<header class="hero"><div class="eyebrow">study_abroad · 留学申请信息库</div>' +
      "<h1>院校数据总览</h1>" +
      '<p class="sub">数据来自本地 MySQL，导出于 ' + esc(data.generated_at) +
      "；点击学校进入详情</p></header>";

    // 学校卡片
    h += '<section><div class="uni-grid">' + data.universities.map(function (u) {
      var nProg = u.programs.length;
      var nMod = Object.keys(u.modules || {}).length;
      var dead = (u.source_status || []).filter(function (s) { return s.status === "dead"; }).length;
      return '<a class="uni-card" href="#/u/' + esc(u.code) + '">' +
        '<span class="country">' + esc(u.country) + " · " + esc(u.city || "") + "</span>" +
        "<h3>" + esc(u.name_en) + "</h3>" +
        '<span class="zh">' + esc(u.name_zh || "") + " · " + esc(u.term_system || "") + "</span>" +
        '<div class="nums"><div><b>' + nProg + "</b><span>专业</span></div>" +
        "<div><b>" + nMod + "</b><span>模块</span></div>" +
        "<div><b>" + (u.calendar.length ? "✓" : "—") + "</b><span>校历</span></div>" +
        "<div><b>" + (dead ? dead + "⚠" : "0") + "</b><span>失效源</span></div></div></a>";
    }).join("") + "</div></section>";

    // 信息页占位：放跨校的重要信息（具体内容待定）
    h += "<section><h2>重要信息</h2>" +
      '<p class="empty">这里预留给跨校的重要信息（申请季提醒、政策变动等），内容待定</p></section>';
    return h;
  };

  /* ---------------- 学校页 ---------------- */
  VIEWS.university = function (uni, filters) {
    var ex = uni.extra || {};
    var chips = [ex.group, ex.ug_programs && "官网本科 " + ex.ug_programs + " 个",
      ex.pgt_programs && "官网授课硕士 " + ex.pgt_programs + " 个", uni.cn_student_note]
      .filter(Boolean).map(function (c) { return '<span class="chip">' + esc(c) + "</span>"; }).join("");
    var h = '<header class="hero"><div class="eyebrow">' + esc(uni.country) + " · " + esc(uni.city || "") + "</div>" +
      "<h1>" + esc(uni.name_en) + (uni.name_zh ? ' <span class="zh">' + esc(uni.name_zh) + "</span>" : "") + "</h1>" +
      '<p class="sub">' + esc(uni.term_system || "") +
      (uni.website ? ' · <a href="' + esc(uni.website) + '" target="_blank" rel="noopener">' +
        esc(uni.website.replace(/^https?:\/\//, "")) + "</a>" : "") + "</p>" +
      (chips ? '<div class="chips">' + chips + "</div>" : "") + "</header>";

    h += VIEWS._calendarSection(uni);
    h += VIEWS._facultyGrid(uni);
    h += fold("未截止的关键日期", VIEWS._deadlineBody(uni));
    h += fold("语言要求分档", VIEWS._bandBody(uni));
    h += fold("中国学生政策要点", VIEWS._policyBody(uni));
    return h;
  };

  /* 折叠板块：默认收起，点标题展开 */
  function fold(title, body, open) {
    if (!body) return "";
    return '<details class="fold"' + (open ? " open" : "") + ">" +
      "<summary><h2>" + title + "</h2></summary>" +
      '<div class="fold-body">' + body + "</div></details>";
  }

  /* ---- 学院聚合：专业挂在系上时向上归并到顶层学院 ---- */
  VIEWS.facTop = function (uni) {
    var byId = {};
    (uni.faculties || []).forEach(function (f) { byId[f.id] = f; });
    function topOf(id) {
      var cur = byId[id];
      while (cur && cur.parent_id && byId[cur.parent_id]) cur = byId[cur.parent_id];
      return cur || null;
    }
    return { byId: byId, topOf: topOf };
  };

  /* 学院卡片（学校页）：顶层学院 + 本硕专业数 */
  VIEWS._facultyGrid = function (uni) {
    var ft = VIEWS.facTop(uni);
    var agg = {};   // topId -> {fac, n, ug, pgt}
    uni.programs.forEach(function (p) {
      var top = p.faculty_id != null ? ft.topOf(p.faculty_id) : null;
      var key = top ? top.id : 0;
      var a = agg[key] || (agg[key] = { fac: top, n: 0, ug: 0, pgt: 0 });
      a.n += 1;
      if (p.level === "UG") a.ug += 1; else a.pgt += 1;
    });
    var keys = Object.keys(agg).sort(function (a, b) {
      return agg[b].n - agg[a].n;
    });
    if (!keys.length) return "<section><h2>学院</h2><p class='empty'>暂无专业数据</p></section>";
    return "<section><h2>学院</h2>" +
      '<p class="h2note">共 ' + uni.programs.length + " 个专业已入库 · 点击学院查看专业列表</p>" +
      '<div class="uni-grid">' + keys.map(function (k) {
        var a = agg[k];
        var nameEn = a.fac ? a.fac.name_en : "未归类";
        var nameZh = a.fac ? (a.fac.name_zh || "") : "院系信息待补";
        return '<a class="uni-card" href="#/u/' + esc(uni.code) + "/f/" + k + '">' +
          "<h3>" + esc(nameEn) + "</h3>" +
          '<span class="zh">' + esc(nameZh) + "</span>" +
          '<div class="nums"><div><b>' + a.n + "</b><span>专业</span></div>" +
          "<div><b>" + a.ug + "</b><span>本科</span></div>" +
          "<div><b>" + a.pgt + "</b><span>硕士</span></div></div></a>";
      }).join("") + "</div></section>";
  };

  /* ---------------- 学院页 ---------------- */
  VIEWS.faculty = function (uni, facId, filters) {
    var ft = VIEWS.facTop(uni);
    var fac = facId ? ft.byId[facId] : null;
    var progs = uni.programs.filter(function (p) {
      var top = p.faculty_id != null ? ft.topOf(p.faculty_id) : null;
      return (top ? top.id : 0) === facId;
    });
    var h = '<header class="hero"><div class="eyebrow">' +
      esc(uni.name_zh || uni.name_en) + " · 学院</div>" +
      "<h1>" + esc(fac ? fac.name_en : "未归类专业") +
      (fac && fac.name_zh ? ' <span class="zh">' + esc(fac.name_zh) + "</span>" : "") + "</h1>" +
      (fac && fac.url ? '<p class="sub"><a href="' + esc(fac.url) +
        '" target="_blank" rel="noopener">学院官网 ↗</a></p>' : "") + "</header>";
    return h + VIEWS._programSection(uni, filters, progs);
  };

  /* 专业列表（筛选 + 表格）；progs 为该视图下的专业集合（学院页传子集） */
  VIEWS._programSection = function (uni, f, progs) {
    f = f || { level: "all", fac: "all", q: "" };
    progs = progs || uni.programs;
    var facs = {};
    progs.forEach(function (p) { if (p.faculty_name) facs[p.faculty_name] = 1; });
    var facOpts = Object.keys(facs).sort().map(function (n) {
      return '<option value="' + esc(n) + '"' + (f.fac === n ? " selected" : "") + ">" + esc(n) + "</option>";
    }).join("");

    var q = (f.q || "").toLowerCase();
    var rows = progs.filter(function (p) {
      if (f.level !== "all" && p.level !== f.level) return false;
      if (f.fac !== "all" && p.faculty_name !== f.fac) return false;
      if (q && !((p.name_en || "").toLowerCase().indexOf(q) >= 0 ||
                 (p.name_zh || "").indexOf(f.q) >= 0)) return false;
      return true;
    });

    var h = "<section><h2>专业档案</h2>" +
      '<p class="h2note">共 ' + progs.length + " 个已入库 · 点击行进入专业详情</p>" +
      '<div class="filterbar">' +
      '<div class="seg" data-filter="level">' +
      ["all|本硕", "PGT|硕士", "UG|本科"].map(function (s) {
        var kv = s.split("|");
        return '<button data-v="' + kv[0] + '"' + (f.level === kv[0] ? ' class="on"' : "") + ">" + kv[1] + "</button>";
      }).join("") + "</div>" +
      (Object.keys(facs).length > 1
        ? '<select data-filter="fac"><option value="all">全部院系</option>' + facOpts + "</select>" : "") +
      '<input type="search" data-filter="q" value="' + esc(f.q || "") + '" placeholder="搜索专业名…" aria-label="搜索专业">' +
      '<span class="count">' + rows.length + " / " + progs.length + "</span></div>";

    if (!rows.length) return h + '<p class="empty">没有匹配的专业</p></section>';

    var showFac = Object.keys(facs).length > 1;  // 院系只有一个时列是纯重复，不显示
    h += '<div class="scroll"><table><tr><th>专业</th><th>层次</th>' +
      (showFac ? "<th>院系</th>" : "") +
      "<th>国际学费</th><th>语言</th><th>模块</th><th>最近截止</th></tr>";
    rows.forEach(function (p) {
      var d = p.detail || {};
      var band = (uni.language_bands || []).filter(function (b) { return b.band_code === d.language_band; })[0];
      var ielts = d.ielts_overall || (band && band.ielts_overall);
      var dl = UI.progDeadline(p);
      h += '<tr class="click" data-href="#/u/' + esc(uni.code) + "/p/" + p.id + '">' +
        "<td>" + esc(p.name_en) + (p.name_zh ? '<span class="sub">' + esc(p.name_zh) + "</span>" : "") + "</td>" +
        "<td>" + (UI.LEVEL[p.level] || p.level) + "</td>" +
        (showFac ? "<td>" + esc(p.faculty_name || "—") + "</td>" : "") +
        '<td class="num">' + (UI.money(d.tuition_intl, d.currency) || "—") + "</td>" +
        '<td class="num">' + (ielts ? "IELTS " + ielts : "—") + "</td>" +
        '<td class="num">' + (p.modules.length || "—") + "</td>" +
        "<td>" + dl.html + "</td></tr>";
    });
    return h + "</table></div></section>";
  };

  VIEWS._deadlineBody = function (uni) {
    var rows = uni.deadlines.map(function (d) { return { d: d, prog: null }; });
    uni.programs.forEach(function (p) {
      p.deadlines.forEach(function (d) { rows.push({ d: d, prog: p }); });
    });
    var now = new Date();
    var future = rows.filter(function (r) { return new Date(r.d.deadline_at) >= now; });
    future.sort(function (a, b) { return a.d.deadline_at < b.d.deadline_at ? -1 : 1; });
    if (!future.length) return "";
    return '<p class="h2note">最近 15 项 · 已截止的记录在各专业详情页仍可见</p><div class="dl-list">' +
      future.slice(0, 15).map(function (r) {
        var d = r.d;
        var title = r.prog
          ? '<a href="#/u/' + esc(uni.code) + "/p/" + r.prog.id + '">' + esc(r.prog.name_en) + "</a> — " + (UI.AUD[d.audience] || "")
          : (UI.DLTYPE[d.deadline_type] || d.deadline_type);
        return '<div class="dl"><span class="dl-date">' + d.deadline_at.slice(0, 10) + "</span>" +
          '<span class="dl-what">' + title + "<small>" + (d.note ? esc(d.note) : "") + "</small></span>" +
          UI.dlStatus(d.deadline_at) + "</div>";
      }).join("") + "</div>";
  };

  VIEWS._calendarSection = function (uni) {
    if (!uni.calendar.length) {
      return "<section><h2>学期日历</h2>" +
        '<p class="empty">校历未采集（官网未公布或来源页尚未解析）</p></section>';
    }
    var byYear = {};
    uni.calendar.forEach(function (e) {
      (byYear[e.academic_year] = byYear[e.academic_year] || []).push(e);
    });
    // 只显示当前学年和下一学年（更远的先留在库里）
    var now = new Date(), sy = now.getMonth() + 1 >= 9 ? now.getFullYear() : now.getFullYear() - 1;
    var wanted = [sy, sy + 1].map(function (y) {
      return y + "/" + String((y + 1) % 100).padStart(2, "0");
    });
    var years = Object.keys(byYear).filter(function (y) { return wanted.indexOf(y) >= 0; });
    if (!years.length) years = Object.keys(byYear);   // 全不匹配时兜底全显示
    var h = "<section><h2>学期日历</h2>";
    years.sort().forEach(function (y) {
      h += "<h3>" + esc(y) + " 学年</h3>" +
        '<div class="scroll"><table><tr><th>起</th><th>止</th><th>事项</th><th>类型</th></tr>';
      byYear[y].forEach(function (e) {
        var t = UI.ETYPE[e.event_type] || [e.event_type, "teach"];
        h += "<tr><td class='date'>" + e.start_date + "</td><td class='date'>" + (e.end_date || "—") +
          "</td><td>" + esc(e.name) + "</td><td><span class='etype " + t[1] + "'>" + t[0] + "</span></td></tr>";
      });
      h += "</table></div>";
    });
    return h + "</section>";
  };

  VIEWS._bandBody = function (uni) {
    if (!uni.language_bands.length) return "";
    return '<p class="h2note">专业列表的"语言"列即按档位换算</p>' +
      '<div class="scroll"><table><tr><th>档位</th><th>IELTS 总分</th><th>单项</th><th>说明</th></tr>' +
      uni.language_bands.map(function (b) {
        var each = b.ielts_detail && b.ielts_detail.minimum_each;
        return "<tr><td><b>" + esc(b.band_code) + "</b></td>" +
          "<td class='num'>" + (b.ielts_overall || "—") + "</td>" +
          "<td class='num'>" + (each || "—") + "</td>" +
          "<td>" + esc((b.band_label || "").replace(/^Level \d ?/, "")) + "</td></tr>";
      }).join("") + "</table></div>";
  };

  VIEWS._policyBody = function (uni) {
    var c = uni.china_policy;
    if (!c) return "";
    var h = '<p class="h2note">' + esc(c.entry_year) + " Entry</p><div class='policy'>";
    h += "<p style='margin:0'>高考成绩：" +
      (c.gaokao_accepted ? "<span class='yes'>接受</span>" : "<span class='no'>不接受</span>直接申请本科") +
      (c.gaokao_req ? " — " + esc(c.gaokao_req) : "") + "</p>";
    if (c.ug_pathway) h += "<p><b>本科路径：</b>" + esc(c.ug_pathway) + "</p>";
    if (c.pgt_gpa_rule) h += "<p><b>硕士均分：</b>" + esc(c.pgt_gpa_rule) + "</p>";
    var notes = [];
    if (c.agent_list && c.agent_list.note) notes.push(esc(c.agent_list.note));
    if (c.china_office) notes.push(esc(c.china_office));
    if (notes.length) h += '<p class="note">' + notes.join("；") + "</p>";
    return h + "</div>";
  };

  /* ---------------- 专业详情页 ---------------- */
  VIEWS.program = function (uni, prog) {
    var d = prog.detail || {};
    var band = (uni.language_bands || []).filter(function (b) { return b.band_code === d.language_band; })[0];
    var extraNote = d.extra && d.extra.note;

    var h = '<header class="hero"><div class="eyebrow">' +
      (UI.LEVEL[prog.level] || prog.level) + (prog.ucas_code ? " · UCAS " + esc(prog.ucas_code) : "") + "</div>" +
      "<h1>" + esc(prog.name_en) + "</h1>" +
      '<p class="sub">' + esc([prog.name_zh, prog.faculty_name, prog.duration].filter(Boolean).join(" · ")) +
      (prog.url ? ' · <a href="' + esc(prog.url) + '" target="_blank" rel="noopener">官网专业页 ↗</a>' : "") + "</p></header>";

    h += '<div class="detail-grid"><div class="facts">';
    if (extraNote) h += '<div class="warnbox">⚠ ' + esc(extraNote) + "</div>";
    h += '<div class="card"><dl class="kv">';
    h += "<dt>学费 " + esc((d.extra && d.extra.fee_year_label) || d.entry_year || "") + "</dt><dd>" +
      (d.tuition_intl != null ? '<span class="fee-big">' + UI.money(d.tuition_intl, d.currency) + "</span> 国际" : "未获取") +
      (d.tuition_home != null ? '<br><span style="color:var(--ink-soft)">本土 ' + UI.money(d.tuition_home, d.currency) + "</span>" : "") + "</dd>";
    var ielts = d.ielts_overall || (band && band.ielts_overall);
    var each = (d.ielts_detail && d.ielts_detail.minimum_each) ||
               (band && band.ielts_detail && band.ielts_detail.minimum_each);
    if (ielts) h += "<dt>语言要求" + (d.language_band ? "（" + esc(d.language_band) + " 档）" : "") +
      '</dt><dd><span class="ielts">IELTS ' + ielts + "</span>" + (each ? " 单项 ≥ " + each : "") + "</dd>";
    if (d.entry_req_text) h += "<dt>学术要求</dt><dd>" + esc(d.entry_req_text) + "</dd>";
    if (d.china_req_text) h += "<dt>中国学生要求</dt><dd>" + esc(d.china_req_text) + "</dd>";
    if (d.extra && d.extra.admissions_test) h += "<dt>入学测试</dt><dd>" + esc(d.extra.admissions_test) + "</dd>";
    if (d.app_open_date) h += "<dt>开放申请</dt><dd>" + d.app_open_date + "</dd>";
    h += "</dl></div>";

    if (prog.deadlines.length) {
      h += '<div class="card"><dl class="kv"><dt>申请截止</dt>' + prog.deadlines.map(function (dd) {
        return "<dd>" + dd.deadline_at.slice(0, 10) + " · " + (UI.AUD[dd.audience] || "") +
          (dd.note ? '<span class="sub" style="display:block;font-size:12px;color:var(--ink-soft)">' + esc(dd.note) + "</span>" : "") +
          " " + UI.dlStatus(dd.deadline_at) + "</dd>";
      }).join("") + "</dl></div>";
    }
    h += "</div>";  /* /facts */

    /* 模块表 */
    h += "<div>";
    var groups = { core: [], optional: [], elective: [] };
    prog.modules.forEach(function (pm) {
      var m = uni.modules[pm.module_id];
      if (m) groups[pm.module_type || "optional"].push(m);
    });
    h += UI.assLegend;
    ["core", "optional", "elective"].forEach(function (g) {
      if (!groups[g].length) return;
      h += "<h3>" + UI.MODTYPE[g] + "模块（" + groups[g].length + "）</h3>" +
        '<div class="scroll"><table><tr><th>代码</th><th>模块</th><th>学分</th><th>考核</th></tr>';
      groups[g].sort(function (a, b) { return (a.code || "").localeCompare(b.code || ""); })
        .forEach(function (m) {
          h += '<tr class="click" data-href="#/u/' + esc(uni.code) + "/m/" + m.id + '">' +
            '<td class="mcode">' + esc(m.code || "—") + "</td>" +
            "<td>" + esc(m.name_en) +
            (m.leader ? '<span class="sub">' + esc(m.leader) + "</span>" : "") + "</td>" +
            '<td class="num">' + (m.credits || "—") + "</td>" +
            "<td>" + UI.assBar(m.assessment) + "</td></tr>";
        });
      h += "</table></div>";
    });
    if (!prog.modules.length) h += '<p class="empty">模块列表未获取</p>';
    h += "</div></div>";  /* /detail-grid */
    return h;
  };

  /* ---------------- 模块详情页 ---------------- */
  VIEWS.module = function (uni, mod) {
    var ex = mod.extra || {};
    var h = '<header class="hero"><div class="eyebrow">课程模块 · ' + esc(mod.code || "无代码") + "</div>" +
      "<h1>" + esc(mod.name_en) + (mod.name_zh ? ' <span class="zh">' + esc(mod.name_zh) + "</span>" : "") + "</h1>" +
      '<p class="sub">' + esc([mod.level, mod.semester, mod.credits && mod.credits + " 学分",
        mod.leader && "负责人 " + mod.leader].filter(Boolean).join(" · ")) +
      (mod.url ? ' · <a href="' + esc(mod.url) + '" target="_blank" rel="noopener">Module Catalogue ↗</a>' : "") +
      "</p>";
    if (mod.assessment) h += "<div>" + UI.assBar(mod.assessment) + "</div>";
    h += "</header>";

    /* 所属专业 */
    var parents = uni.programs.filter(function (p) {
      return p.modules.some(function (pm) { return pm.module_id === mod.id; });
    });
    if (parents.length) {
      h += '<section><p class="h2note" style="margin:14px 0 0">出现在 ' + parents.length + " 个专业：" +
        parents.map(function (p) {
          var t = p.modules.filter(function (pm) { return pm.module_id === mod.id; })[0];
          return '<a href="#/u/' + esc(uni.code) + "/p/" + p.id + '">' + esc(p.name_en) + "</a>（" +
            (UI.MODTYPE[t.module_type] || "") + "）";
        }).join(" · ") + "</p></section>";
    }

    if (mod.prerequisites) {
      h += "<section><h2>先修要求</h2><div class='policy'>" + esc(mod.prerequisites) + "</div></section>";
    }

    h += "<section><h2>课程大纲</h2>";
    if (mod.description && mod.description.length > 120) {
      h += '<p class="h2note">官网 Module Catalogue 完整公开内容</p>' +
        '<div class="syllabus">' + esc(mod.description) + "</div>";
    } else {
      h += '<p class="empty">' + esc(mod.description || "大纲未采集") + "</p>";
    }
    h += "</section>";

    if (ex.reading_list) {
      h += "<section><h2>阅读书单</h2><div class='policy'>官方公开书单：" +
        '<a href="' + esc(ex.reading_list) + '" target="_blank" rel="noopener">' + esc(ex.reading_list) + "</a></div></section>";
    }

    /* 课程内容（module_contents，含手动录入） */
    var cs = mod.contents || [];
    h += "<section><h2>课程内容与经验</h2>" +
      '<p class="h2note">module_contents 表 · 自动采集与手动录入共存，注意来源标识</p>';
    if (cs.length) {
      var byType = {};
      cs.forEach(function (c) { (byType[c.content_type] = byType[c.content_type] || []).push(c); });
      Object.keys(byType).forEach(function (t) {
        h += "<h3>" + (UI.CONTENT_TYPE[t] || t) + "</h3>" + byType[t].map(function (c) {
          return '<div class="content-item"><div class="head"><b>' +
            (c.seq_no ? "第 " + c.seq_no + " 项 · " : "") + esc(c.title) + "</b>" +
            UI.srcBadge(c.source, c.verified) + "</div>" +
            (c.body ? '<div class="body">' + esc(c.body) + "</div>" : "") +
            '<div class="meta">' + esc([c.source_note, c.entry_year && c.entry_year + " 学年",
              c.added_by && "录入 " + c.added_by].filter(Boolean).join(" · ")) +
            (c.url ? ' · <a href="' + esc(c.url) + '" target="_blank" rel="noopener">链接</a>' : "") + "</div></div>";
        }).join("");
      });
    } else {
      h += '<p class="empty">暂无记录 — 可通过 INSERT module_contents 手动录入（周主题/备考经验/学生评价等）</p>';
    }
    return h + "</section>";
  };

  window.VIEWS = VIEWS;
})();
