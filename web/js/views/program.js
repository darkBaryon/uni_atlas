/* ============================================================
   views/program.js — 专业详情页
   ============================================================ */
(function () {
  "use strict";
  var UI = window.UI, esc = UI.esc;
  var VIEWS = window.VIEWS = window.VIEWS || {};

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
})();
