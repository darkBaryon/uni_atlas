/* ============================================================
   views/program.js — 专业详情页（含培养计划路线图 _planSection）
   ============================================================ */
(function () {
  "use strict";
  var UI = window.UI, esc = UI.esc;
  var VIEWS = window.VIEWS = window.VIEWS || {};

  /* 培养计划路线图：逐年逐学期修课序列 + 先修（数据来自 program_plans）。
     课程码可点进详情；"A or B"/通识活动整块显示；多变体（主修×起始学期）折叠。 */
  VIEWS._planSection = function (uni, prog) {
    var plans = prog.plans || [];
    if (!plans.length) return "";
    var modByCode = {};
    Object.keys(uni.modules).forEach(function (id) {
      var m = uni.modules[id];
      if (m.code) modByCode[m.code] = m.id;
    });
    // 单门课/活动卡片：真课程（有码可点）与占位活动（通识/选修）视觉分级
    function item(it) {
      var mid = it.code && modByCode[it.code];
      var isCourse = !!it.code;
      var codeHtml = it.code
        ? (mid ? '<a class="pcode" href="#/u/' + esc(uni.code) + "/m/" + mid + '">' + esc(it.code) + "</a>"
               : '<span class="pcode dead">' + esc(it.code) + "</span>")
        : "";
      var pre = it.prereq
        ? '<span class="ppre" title="先修">↳ ' + esc(it.prereq) + "</span>" : "";
      return '<div class="pitem' + (isCourse ? "" : " activity") + '">' +
        '<div class="pitem-main">' + codeHtml +
        '<span class="pname">' + esc(it.label || "") + "</span>" +
        (it.credits ? '<span class="pcr">' + it.credits + "</span>" : "") +
        "</div>" + pre + "</div>";
    }
    function one(p, open) {
      var years = (p.plan && p.plan.years) || [];
      // 按学年分组，同一年的各 term 并排
      var byYear = {};
      years.forEach(function (t) { (byYear[t.year] = byYear[t.year] || []).push(t); });
      var body = Object.keys(byYear).sort(function (a, b) { return a - b; }).map(function (yr) {
        var terms = byYear[yr].sort(function (a, b) { return a.term - b.term; });
        var cols = terms.map(function (t) {
          var cr = t.items.reduce(function (s, it) { return s + (it.credits || 0); }, 0);
          return '<div class="pterm"><div class="pterm-hd">Term ' + t.term +
            '<span class="pterm-cr">' + cr + " UOC</span></div>" +
            t.items.map(item).join("") + "</div>";
        }).join("");
        return '<div class="pyear"><div class="pyear-tag">Year ' + esc(yr) + "</div>" +
          '<div class="pterms">' + cols + "</div></div>";
      }).join("");
      return '<details class="fold planfold"' + (open ? " open" : "") +
        ' data-fold="plan-' + esc(p.variant_label) + '"><summary>' +
        '<span class="pvar">' + esc(p.variant_label) + "</span>" +
        (p.source_url ? '<a class="pdf" href="' + esc(p.source_url) +
          '" target="_blank" rel="noopener">官方 PDF ↗</a>' : "") +
        '</summary><div class="planroad">' + body + "</div></details>";
    }
    return '<section><h2>培养计划</h2>' +
      '<p class="h2note">逐年逐学期修课路线 · 课程码可点开看详情 · ↳ 标注先修</p>' +
      plans.map(function (p, i) { return one(p, i === 0); }).join("") + "</section>";
  };

  VIEWS.program = function (uni, prog) {
    var d = prog.detail || {};
    var band = (uni.language_bands || []).filter(function (b) { return b.band_code === d.language_band; })[0];
    var extraNote = d.extra && d.extra.note;

    var h = '<header class="hero"><div class="eyebrow">' +
      (UI.LEVEL[prog.level] || prog.level) + (prog.ucas_code ? " · UCAS " + esc(prog.ucas_code) : "") + "</div>" +
      "<h1>" + esc(prog.name_en) + "</h1>" +
      '<p class="sub">' + esc([prog.name_zh, prog.faculty_name, prog.duration].filter(Boolean).join(" · ")) +
      (prog.url ? ' · <a href="' + esc(prog.url) + '" target="_blank" rel="noopener">官网专业页 ↗</a>' : "") + "</p></header>";

    if (extraNote) h += '<div class="warnbox">⚠ ' + esc(extraNote) + "</div>";

    /* 培养计划路线图（辅导核心，整宽置顶） */
    h += VIEWS._planSection(uni, prog);

    /* 课程模块（整宽） */
    var groups = { core: [], optional: [], elective: [] };
    prog.modules.forEach(function (pm) {
      var m = uni.modules[pm.module_id];
      if (m) groups[pm.module_type || "optional"].push(m);
    });
    if (prog.modules.length) {
      h += "<section><h2>课程模块</h2>" + UI.assLegend;
      ["core", "optional", "elective"].forEach(function (g) {
        if (!groups[g].length) return;
        h += "<h3>" + UI.MODTYPE[g] + "（" + groups[g].length + "）</h3>" +
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
      h += "</section>";
    }

    /* 申请参考（学费/语言/截止）——辅导定位下默认折叠，数据仍在库 */
    var ielts = d.ielts_overall || (band && band.ielts_overall);
    var each = (d.ielts_detail && d.ielts_detail.minimum_each) ||
               (band && band.ielts_detail && band.ielts_detail.minimum_each);
    var app = "";
    if (d.tuition_intl != null) app += "<dt>学费 " + esc((d.extra && d.extra.fee_year_label) || d.entry_year || "") +
      '</dt><dd><span class="fee-big">' + UI.money(d.tuition_intl, d.currency) + "</span> 国际" +
      (d.tuition_home != null ? ' · 本土 ' + UI.money(d.tuition_home, d.currency) : "") + "</dd>";
    if (ielts) app += "<dt>语言要求" + (d.language_band ? "（" + esc(d.language_band) + " 档）" : "") +
      '</dt><dd><span class="ielts">IELTS ' + ielts + "</span>" + (each ? " 单项 ≥ " + each : "") + "</dd>";
    if (d.entry_req_text) app += "<dt>学术要求</dt><dd>" + esc(d.entry_req_text) + "</dd>";
    if (d.china_req_text) app += "<dt>中国学生要求</dt><dd>" + esc(d.china_req_text) + "</dd>";
    if (d.extra && d.extra.admissions_test) app += "<dt>入学测试</dt><dd>" + esc(d.extra.admissions_test) + "</dd>";
    if (d.app_open_date) app += "<dt>开放申请</dt><dd>" + d.app_open_date + "</dd>";
    if (prog.deadlines.length) app += "<dt>申请截止</dt>" + prog.deadlines.map(function (dd) {
      return "<dd>" + dd.deadline_at.slice(0, 10) + " · " + (UI.AUD[dd.audience] || "") +
        (dd.note ? '<span class="sub">' + esc(dd.note) + "</span>" : "") +
        " " + UI.dlStatus(dd.deadline_at) + "</dd>";
    }).join("");
    if (app) {
      h += '<details class="fold"' + (UI.SHOW_APP ? " open" : "") +
        ' data-fold="prog-app"><summary><h2>申请参考</h2>' +
        '<span class="fold-count">学费 · 语言 · 截止</span></summary>' +
        '<div class="fold-body"><dl class="kv appkv">' + app + "</dl></div></details>";
    }
    return h;
  };

})();
