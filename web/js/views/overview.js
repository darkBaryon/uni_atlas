/* ============================================================
   views/overview.js — 总览页（吃 index 摘要，按地区分组）
   ============================================================ */
(function () {
  "use strict";
  var UI = window.UI, esc = UI.esc;
  var VIEWS = window.VIEWS = window.VIEWS || {};

  var REGION = { UK: "英国", AU: "澳大利亚", HK: "香港" };
  VIEWS.REGION = REGION;

  VIEWS.overview = function (index) {
    var h = '<header class="hero"><div class="eyebrow">study_abroad · 留学辅导课程库</div>' +
      "<h1>院校总览</h1>" +
      '<p class="sub">数据导出于 ' + esc(index.generated_at) + "；点击学校进入</p></header>";

    // 按地区分组（顺序：英国 → 澳大利亚 → 香港 → 其他）
    var groups = {}, order = [];
    index.universities.forEach(function (u) {
      var key = u.country || "其他";
      if (!groups[key]) { groups[key] = []; order.push(key); }
      groups[key].push(u);
    });
    order.sort(function (a, b) {
      var rank = ["UK", "AU", "HK"];
      return (rank.indexOf(a) + 99 * (rank.indexOf(a) < 0)) -
             (rank.indexOf(b) + 99 * (rank.indexOf(b) < 0));
    });

    order.forEach(function (key) {
      h += '<section id="region-' + esc(key) + '"><h2>' + esc(REGION[key] || key) + "</h2>" +
        '<div class="uni-grid">' + groups[key].map(function (u) {
          return '<a class="uni-card" href="#/u/' + esc(u.code) + '">' +
            '<span class="country">' + esc(u.city || "") + "</span>" +
            "<h3>" + esc(u.name_en) + "</h3>" +
            '<span class="zh">' + esc(u.name_zh || "") + " · " + esc(u.term_system || "") + "</span>" +
            '<div class="nums"><div><b>' + u.n_programs + "</b><span>专业</span></div>" +
            "<div><b>" + u.n_modules + "</b><span>课程</span></div>" +
            "<div><b>" + (u.has_calendar ? "✓" : "—") + "</b><span>校历</span></div>" +
            "<div><b>" + (u.dead_sources ? u.dead_sources + "⚠" : "0") + "</b><span>失效源</span></div></div></a>";
        }).join("") + "</div></section>";
    });

    h += "<section><h2>重要信息</h2>" +
      '<p class="empty">这里预留给跨校的重要信息（考试季提醒、高需求课程等），内容待定</p></section>';
    return h;
  };
})();
