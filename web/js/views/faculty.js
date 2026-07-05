/* ============================================================
   views/faculty.js — 学院页 + 系页
   ============================================================ */
(function () {
  "use strict";
  var UI = window.UI, esc = UI.esc;
  var VIEWS = window.VIEWS = window.VIEWS || {};

  /* ---------------- 学院页：有系放系卡片，没系直接放课程列表 ---------------- */
  VIEWS.faculty = function (uni, facId, filters) {
    var ft = VIEWS.facTop(uni);
    var fac = facId ? ft.byId[facId] : null;
    var h = '<header class="hero"><div class="eyebrow">' +
      esc(uni.name_zh || uni.name_en) + " · 学院</div>" +
      "<h1>" + esc(fac ? fac.name_en : "未归类课程") +
      (fac && fac.name_zh ? ' <span class="zh">' + esc(fac.name_zh) + "</span>" : "") + "</h1>" +
      (fac && fac.url ? '<p class="sub"><a href="' + esc(fac.url) +
        '" target="_blank" rel="noopener">学院官网 ↗</a></p>' : "") + "</header>";

    // 下属系（有课程的才算）
    var depts = (uni.faculties || []).filter(function (f) { return f.parent_id === facId; });
    var progCount = {};
    uni.programs.forEach(function (p) {
      if (p.faculty_id != null) {
        progCount[p.faculty_id] = (progCount[p.faculty_id] || 0) + 1;
      }
    });
    depts = depts.filter(function (d) { return progCount[d.id]; });

    // 挂在学院本级的课程（没有系、或学院直属的）
    var direct = uni.programs.filter(function (p) {
      if (facId === 0) {   // 未归类
        var top = p.faculty_id != null ? ft.topOf(p.faculty_id) : null;
        return !top;
      }
      return p.faculty_id === facId;
    });

    if (depts.length) {
      h += "<section><h2>系</h2>" +
        '<p class="h2note">点击进入系页</p><div class="uni-grid">' +
        depts.map(function (d) {
          var ug = 0, pgt = 0;
          uni.programs.forEach(function (p) {
            if (p.faculty_id === d.id) { if (p.level === "UG") ug++; else pgt++; }
          });
          return '<a class="uni-card" href="#/u/' + esc(uni.code) + "/d/" + d.id + '">' +
            "<h3>" + esc(d.name_en) + "</h3>" +
            '<span class="zh">' + esc(d.name_zh || "") + "</span>" +
            '<div class="nums"><div><b>' + (ug + pgt) + "</b><span>专业</span></div>" +
            "<div><b>" + ug + "</b><span>本科</span></div>" +
            "<div><b>" + pgt + "</b><span>硕士</span></div></div></a>";
        }).join("") + "</div></section>";
      if (direct.length) {
        h += VIEWS._programSection(uni, filters, direct, "学院直属专业");
      }
      return h;
    }
    var facIds = {}; facIds[facId] = 1;
    (uni.faculties || []).forEach(function (f) { if (f.parent_id === facId) facIds[f.id] = 1; });
    // 无系的学院：课程列表在上、专业列表在下
    h += VIEWS._moduleSection(uni, direct, facIds);
    return h + VIEWS._programSection(uni, filters, direct, "专业列表");
  };

  /* ---------------- 系页：课程列表在上，专业列表在下 ---------------- */
  VIEWS.dept = function (uni, deptId, filters) {
    var ft = VIEWS.facTop(uni);
    var dept = ft.byId[deptId];
    var top = dept && dept.parent_id ? ft.byId[dept.parent_id] : null;
    var progs = uni.programs.filter(function (p) { return p.faculty_id === deptId; });
    var h = '<header class="hero"><div class="eyebrow">' +
      esc(uni.name_zh || uni.name_en) +
      (top ? " · " + esc(top.name_zh || top.name_en) : "") + "</div>" +
      "<h1>" + esc(dept ? dept.name_en : "系") +
      (dept && dept.name_zh ? ' <span class="zh">' + esc(dept.name_zh) + "</span>" : "") + "</h1>" +
      (dept && dept.url ? '<p class="sub"><a href="' + esc(dept.url) +
        '" target="_blank" rel="noopener">官网 ↗</a></p>' : "") + "</header>";
    var facIds = {}; facIds[deptId] = 1;
    // 课程在上、专业在下（辅导镜头：课程是主角）
    h += VIEWS._moduleSection(uni, progs, facIds);
    return h + VIEWS._programSection(uni, filters, progs, "专业列表");
  };
})();
