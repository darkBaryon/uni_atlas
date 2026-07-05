/* ============================================================
   views/_shared.js — 跨视图复用的私有件（最先加载）
   初始化 window.VIEWS；其余视图文件往上挂方法
   foldSec / facTop / _programSection / _moduleSection
   ============================================================ */
(function () {
  "use strict";
  var UI = window.UI, esc = UI.esc;
  var VIEWS = window.VIEWS = window.VIEWS || {};

  /* 带数量徽章的折叠段（专业/课程用）：summary 里标题 + 计数 pill */
  function foldSec(title, count, body, open) {
    // data-fold = 开合状态的保存键：SPA 重渲染（筛选/搜索）后由 app.js 回放
    return '<details class="fold foldsec" data-fold="' + esc(title) + '"' +
      (open ? " open" : "") + ">" +
      "<summary><h2>" + esc(title) + '</h2><span class="fold-count">' +
      esc(count) + "</span></summary>" +
      '<div class="fold-body">' + body + "</div></details>";
  }
  VIEWS._foldSec = foldSec;

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

  /* 课程（模块）列表：专业课表引用 ∪ 按院系归属的官方名单（facIds 给定时） */
  VIEWS._moduleSection = function (uni, progs, facIds) {
    var seen = {}, mods = [];
    progs.forEach(function (p) {
      (p.modules || []).forEach(function (pm) {
        var m = uni.modules[pm.module_id];
        if (m && !seen[m.id]) { seen[m.id] = 1; mods.push(m); }
      });
    });
    if (facIds) {
      Object.keys(uni.modules).forEach(function (id) {
        var m = uni.modules[id];
        if (m.faculty_id != null && facIds[m.faculty_id] && !seen[m.id]) {
          seen[m.id] = 1; mods.push(m);
        }
      });
    }
    if (!mods.length) {
      var cat = (uni.extra || {}).module_catalogue_url;
      return "<section><h2>课程列表</h2><p class='empty'>" +
        (cat ? '本库未收录该院系课程清单 — 见 <a href="' + esc(cat) +
               '" target="_blank" rel="noopener">官方课程总目录 ↗</a>'
             : "该校未公开课程目录（或尚未找到公开源）") + "</p></section>";
    }
    mods.sort(function (a, b) { return (a.code || "zz").localeCompare(b.code || "zz"); });
    var b = '<p class="h2note">来自本系各专业的课程表 · 点击行看大纲/考核</p>' +
      '<div class="scroll"><table><tr><th>代码</th><th>课程</th><th>学分</th><th>学期</th><th>考核</th></tr>';
    mods.forEach(function (m) {
      b += '<tr class="click" data-href="#/u/' + esc(uni.code) + "/m/" + m.id + '">' +
        '<td class="mcode">' + esc(m.code || "—") + "</td>" +
        "<td>" + esc(m.name_en) +
        (m.name_zh ? '<span class="sub">' + esc(m.name_zh) + "</span>"
                   : (m.leader ? '<span class="sub">' + esc(m.leader) + "</span>" : "")) + "</td>" +
        '<td class="num">' + (m.credits || "—") + "</td>" +
        "<td>" + esc(m.semester || "—") + "</td>" +
        "<td>" + UI.assBar(m.assessment) + "</td></tr>";
    });
    // 课程是主角，默认展开；量大时可手动收起，数量在徽章上一眼可见
    return foldSec("课程列表", mods.length + " 门", b + "</table></div>", true);
  };

  /* 课程列表（筛选 + 表格）；progs 为该视图下的课程集合 */
  VIEWS._programSection = function (uni, f, progs, title) {
    f = f || { level: "all", fac: "all", q: "" };
    progs = progs || uni.programs;
    title = title || "专业列表";
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

    var h = '<p class="h2note">点击行进入专业详情</p>' +
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

    if (!rows.length) return foldSec(title, progs.length + " 个", h + '<p class="empty">没有匹配的专业</p>', true);

    var showFac = Object.keys(facs).length > 1;  // 院系只有一个时列是纯重复，不显示
    h += '<div class="scroll"><table><tr><th>专业</th><th>层次</th>' +
      (showFac ? "<th>院系</th>" : "") +
      (UI.SHOW_APP ? "<th>国际学费</th><th>语言</th>" : "") +
      "<th>课程数</th>" + (UI.SHOW_APP ? "<th>最近截止</th>" : "") + "</tr>";
    rows.forEach(function (p) {
      var d = p.detail || {};
      var band = (uni.language_bands || []).filter(function (b) { return b.band_code === d.language_band; })[0];
      var ielts = d.ielts_overall || (band && band.ielts_overall);
      var dl = UI.progDeadline(p);
      h += '<tr class="click" data-href="#/u/' + esc(uni.code) + "/p/" + p.id + '">' +
        "<td>" + esc(p.name_en) + (p.name_zh ? '<span class="sub">' + esc(p.name_zh) + "</span>" : "") + "</td>" +
        "<td>" + (UI.LEVEL[p.level] || p.level) + "</td>" +
        (showFac ? "<td>" + esc(p.faculty_name || "—") + "</td>" : "") +
        (UI.SHOW_APP ? '<td class="num">' + (UI.money(d.tuition_intl, d.currency) || "—") + "</td>" +
                       '<td class="num">' + (ielts ? "IELTS " + ielts : "—") + "</td>" : "") +
        '<td class="num">' + (p.modules.length || "—") + "</td>" +
        (UI.SHOW_APP ? "<td>" + dl.html + "</td>" : "") + "</tr>";
    });
    // 专业是系页主内容，默认展开
    return foldSec(title, progs.length + " 个", h + "</table></div>", true);
  };
})();
