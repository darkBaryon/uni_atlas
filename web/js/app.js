/* ============================================================
   app.js — hash 路由与状态
   路由:  #/                     概览
          #/u/{code}             学校页
          #/u/{code}/p/{id}      专业详情
          #/u/{code}/m/{id}      模块详情
   file:// 直接打开可用；筛选状态存内存（切换视图后保留）
   ============================================================ */
(function () {
  "use strict";
  var DATA = window.STUDY_ABROAD_DATA;
  var app = document.getElementById("app");
  var nav = document.getElementById("nav");
  var foot = document.getElementById("foot");

  if (!DATA || !DATA.universities || !DATA.universities.length) {
    app.innerHTML = '<p class="empty">没有数据 — 请先运行 <code>python3 web/export.py</code> 生成 data.js，再刷新本页</p>';
    return;
  }

  var uniByCode = {};
  DATA.universities.forEach(function (u) { uniByCode[u.code] = u; });

  // 每校的专业筛选状态（跨路由保留）
  var filterState = {};

  function parseHash() {
    var seg = (location.hash || "#/").replace(/^#\/?/, "").split("/").filter(Boolean);
    if (!seg.length) return { view: "overview" };
    if (seg[0] === "u" && seg[1]) {
      var uni = uniByCode[seg[1]];
      if (!uni) return { view: "overview" };
      if (seg[2] === "p" && seg[3]) return { view: "program", uni: uni, id: +seg[3] };
      if (seg[2] === "m" && seg[3]) return { view: "module", uni: uni, id: +seg[3] };
      if (seg[2] === "f" && seg[3] != null) return { view: "faculty", uni: uni, id: +seg[3] };
      if (seg[2] === "d" && seg[3] != null) return { view: "dept", uni: uni, id: +seg[3] };
      return { view: "university", uni: uni };
    }
    return { view: "overview" };
  }

  function crumbs(route) {
    var parts = ['<a href="#/">总览</a>'];
    if (route.uni) parts.push('<a href="#/u/' + route.uni.code + '">' + UI.esc(route.uni.name_zh || route.uni.name_en) + "</a>");
    if (route.view === "faculty") {
      var fac = (route.uni.faculties || []).filter(function (x) { return x.id === route.id; })[0];
      parts.push(fac ? UI.esc(fac.name_zh || fac.name_en) : "未归类");
    }
    if (route.view === "dept") {
      var dept = (route.uni.faculties || []).filter(function (x) { return x.id === route.id; })[0];
      if (dept && dept.parent_id) {
        var pf = (route.uni.faculties || []).filter(function (x) { return x.id === dept.parent_id; })[0];
        if (pf) parts.push('<a href="#/u/' + route.uni.code + '/f/' + pf.id + '">' +
          UI.esc(pf.name_zh || pf.name_en) + "</a>");
      }
      parts.push(dept ? UI.esc(dept.name_zh || dept.name_en) : "系");
    }
    if (route.view === "program") parts.push("专业详情");
    if (route.view === "module") parts.push("课程详情");
    return parts.length > 1 ? '<div class="crumbs">' + parts.join("<span>›</span>") + "</div>" : "";
  }

  function render() {
    var route = parseHash();
    var html = crumbs(route);

    if (route.view === "overview") {
      html += VIEWS.overview(DATA);
    } else if (route.view === "university") {
      html += VIEWS.university(route.uni, null);
    } else if (route.view === "faculty") {
      var fk = route.uni.code + "/f" + route.id;
      var f = filterState[fk] || (filterState[fk] = { level: "all", fac: "all", q: "" });
      html += VIEWS.faculty(route.uni, route.id, f);
    } else if (route.view === "dept") {
      var dk = route.uni.code + "/d" + route.id;
      var fd = filterState[dk] || (filterState[dk] = { level: "all", fac: "all", q: "" });
      html += VIEWS.dept(route.uni, route.id, fd);
    } else if (route.view === "program") {
      var prog = route.uni.programs.filter(function (p) { return p.id === route.id; })[0];
      html += prog ? VIEWS.program(route.uni, prog) : '<p class="empty">专业不存在</p>';
    } else if (route.view === "module") {
      var mod = route.uni.modules[route.id];
      html += mod ? VIEWS.module(route.uni, mod) : '<p class="empty">模块不存在</p>';
    }

    app.innerHTML = html;
    if (route.view !== "faculty" && route.view !== "dept") window.scrollTo(0, 0);
    renderNav(route);
    bindEvents(route);
  }

  function renderNav(route) {
    var h = '<a class="brand" href="#/">留学申请信息库</a>' +
      '<a class="tab' + (route.view === "overview" ? " on" : "") + '" href="#/">总览</a>' +
      DATA.universities.map(function (u) {
        var on = route.uni && route.uni.code === u.code;
        return '<a class="tab' + (on ? " on" : "") + '" href="#/u/' + u.code + '">' +
          UI.esc(u.name_zh || u.name_en) + "</a>";
      }).join("");
    nav.innerHTML = h;
  }

  function bindEvents(route) {
    // 可点击表格行
    app.querySelectorAll("tr.click[data-href]").forEach(function (tr) {
      tr.addEventListener("click", function () { location.hash = tr.dataset.href; });
      tr.tabIndex = 0;
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter") location.hash = tr.dataset.href;
      });
    });
    // 学院/系页筛选（改状态后原地重渲染，不动 hash）
    if (route.view === "faculty" || route.view === "dept") {
      var f = filterState[route.uni.code + (route.view === "faculty" ? "/f" : "/d") + route.id];
      app.querySelectorAll('[data-filter="level"] button').forEach(function (b) {
        b.addEventListener("click", function () { f.level = b.dataset.v; render(); });
      });
      var sel = app.querySelector('select[data-filter="fac"]');
      if (sel) sel.addEventListener("change", function () { f.fac = sel.value; render(); });
      var inp = app.querySelector('input[data-filter="q"]');
      if (inp) {
        inp.addEventListener("input", debounce(function () {
          f.q = inp.value;
          var scrollY = window.scrollY;
          render();
          window.scrollTo(0, scrollY);
          var again = app.querySelector('input[data-filter="q"]');
          if (again) { again.focus(); again.setSelectionRange(again.value.length, again.value.length); }
        }, 200));
      }
    }
  }

  function debounce(fn, ms) {
    var t;
    return function () { clearTimeout(t); t = setTimeout(fn, ms); };
  }

  foot.innerHTML = "数据来源：study_abroad 数据库（本地 MySQL）· 导出于 " + UI.esc(DATA.generated_at) +
    " · 更新流程：跑爬虫入库 → <code>./web/start.sh</code> 重新导出并打开";

  window.addEventListener("hashchange", render);
  render();
})();
