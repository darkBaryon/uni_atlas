/* ============================================================
   views/module.js — 模块（课程）详情页
   ============================================================ */
(function () {
  "use strict";
  var UI = window.UI, esc = UI.esc;
  var VIEWS = window.VIEWS = window.VIEWS || {};

  VIEWS.module = function (uni, mod) {
    var ex = mod.extra || {};
    var h = '<header class="hero"><div class="eyebrow">课程模块 · ' + esc(mod.code || "无代码") + "</div>" +
      "<h1>" + esc(mod.name_en) + (mod.name_zh ? ' <span class="zh">' + esc(mod.name_zh) + "</span>" : "") + "</h1>" +
      '<p class="sub">' + esc([mod.level, mod.semester, mod.credits && mod.credits + " 学分",
        mod.leader && "负责人 " + mod.leader].filter(Boolean).join(" · ")) +
      (mod.url ? ' · <a href="' + esc(mod.url) + '" target="_blank" rel="noopener">Module Catalogue ↗</a>' : "") +
      "</p>";
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

    /* 考核构成（辅导核心：定备考重点与旺季排班）——独立模块 */
    if (mod.assessment && mod.assessment.length) {
      h += "<section><h2>考核构成</h2>" + UI.assDetail(mod.assessment) + "</section>";
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
})();
