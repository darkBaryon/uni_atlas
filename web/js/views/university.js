/* ============================================================
   views/university.js — 学校页
   含仅本页使用的私有件：fold / _facultyGrid / _deadlineBody /
   _bandBody / _policyBody
   ============================================================ */
(function () {
  "use strict";
  var UI = window.UI, esc = UI.esc;
  var VIEWS = window.VIEWS = window.VIEWS || {};

  VIEWS.university = function (uni, filters) {
    var ex = uni.extra || {};
    var chips = [ex.group, ex.ug_programs && "官网本科 " + ex.ug_programs + " 个",
      ex.pgt_programs && "官网授课硕士 " + ex.pgt_programs + " 个",
      UI.SHOW_APP && uni.cn_student_note]
      .filter(Boolean).map(function (c) { return '<span class="chip">' + esc(c) + "</span>"; }).join("");
    if (ex.module_catalogue_url) {
      chips += '<a class="chip" href="' + esc(ex.module_catalogue_url) +
        '" target="_blank" rel="noopener">官方课程总目录 ↗</a>';
    }
    var h = '<header class="hero"><div class="eyebrow">' + esc(uni.country) + " · " + esc(uni.city || "") + "</div>" +
      "<h1>" + esc(uni.name_en) + (uni.name_zh ? ' <span class="zh">' + esc(uni.name_zh) + "</span>" : "") + "</h1>" +
      '<p class="sub">' + esc(uni.term_system || "") +
      (uni.website ? ' · <a href="' + esc(uni.website) + '" target="_blank" rel="noopener">' +
        esc(uni.website.replace(/^https?:\/\//, "")) + "</a>" : "") + "</p>" +
      (chips ? '<div class="chips">' + chips + "</div>" : "") + "</header>";

    h += VIEWS._calendarSection(uni);
    h += VIEWS._facultyGrid(uni);
    if (UI.SHOW_APP) {   // 申请域整体收起（辅导业务）；数据在库，开 UI.SHOW_APP 即恢复
      h += fold("未截止的关键日期", VIEWS._deadlineBody(uni));
      h += fold("语言要求分档", VIEWS._bandBody(uni));
      h += fold("中国学生政策要点", VIEWS._policyBody(uni));
    }
    return h;
  };

  /* 折叠板块：默认收起，点标题展开 */
  function fold(title, body, open) {
    if (!body) return "";
    return '<details class="fold"' + (open ? " open" : "") + ">" +
      "<summary><h2>" + title + "</h2></summary>" +
      '<div class="fold-body">' + body + "</div></details>";
  }

  /* 学院卡片（学校页）：顶层学院 + 本硕专业数 */
  VIEWS._facultyGrid = function (uni) {
    var ft = VIEWS.facTop(uni);
    var agg = {};   // topId -> {fac, n, ug, pgt, mods}
    function bucket(facId) {
      var top = facId != null ? ft.topOf(facId) : null;
      var key = top ? top.id : 0;
      return agg[key] || (agg[key] = { fac: top, n: 0, ug: 0, pgt: 0, mods: 0 });
    }
    uni.programs.forEach(function (p) {
      var a = bucket(p.faculty_id);
      a.n += 1;
      if (p.level === "UG") a.ug += 1; else a.pgt += 1;
    });
    // 课程也计入学院卡片——有的学校归属只在课程侧（阿德莱德：学位页无归属）
    Object.keys(uni.modules || {}).forEach(function (id) {
      var m = uni.modules[id];
      if (m.faculty_id != null) bucket(m.faculty_id).mods += 1;
    });
    var keys = Object.keys(agg).filter(function (k) {
      return agg[k].n + agg[k].mods > 0;
    }).sort(function (a, b) { return (agg[b].n - agg[a].n) || (agg[b].mods - agg[a].mods); });
    if (!keys.length) return "<section><h2>学院</h2><p class='empty'>暂无专业数据</p></section>";
    return "<section><h2>学院</h2>" +
      '<p class="h2note">共 ' + uni.programs.length + " 个专业、" +
      Object.keys(uni.modules || {}).length + " 门课程已入库 · 点击学院查看</p>" +
      '<div class="uni-grid">' + keys.map(function (k) {
        var a = agg[k];
        var nameEn = a.fac ? a.fac.name_en : "未归类";
        var nameZh = a.fac ? (a.fac.name_zh || "") : "院系信息待补";
        var nums = a.n > 0
          ? '<div><b>' + a.n + "</b><span>专业</span></div>" +
            "<div><b>" + a.ug + "</b><span>本科</span></div>" +
            "<div><b>" + a.pgt + "</b><span>硕士</span></div>"
          : '<div><b>' + a.mods + "</b><span>课程</span></div>";
        return '<a class="uni-card" href="#/u/' + esc(uni.code) + "/f/" + k + '">' +
          "<h3>" + esc(nameEn) + "</h3>" +
          '<span class="zh">' + esc(nameZh) + "</span>" +
          '<div class="nums">' + nums + "</div></a>";
      }).join("") + "</div></section>";
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
})();
