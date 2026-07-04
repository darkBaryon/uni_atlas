/* ============================================================
   app.js — hash 路由、状态与数据懒加载
   数据架构（与 config/parsers 同构，按校拆分）:
     data/index.js           window.UNI_INDEX   总览摘要（启动即载）
     data/<code>.js          window.UNI_DATA    每校全量（进校页时按需注入）
   路由:  #/                     总览（按地区分组）
          #/u/{code}             学校页
          #/u/{code}/f/{id}      学院页
          #/u/{code}/d/{id}      系页
          #/u/{code}/p/{id}      专业详情
          #/u/{code}/m/{id}      课程详情
   file:// 直接打开可用；筛选状态存内存（切换视图后保留）
   ============================================================ */
(function () {
  "use strict";
  var INDEX = window.UNI_INDEX;
  var app = document.getElementById("app");
  var nav = document.getElementById("nav");
  var foot = document.getElementById("foot");

  if (!INDEX || !INDEX.universities || !INDEX.universities.length) {
    app.innerHTML = '<p class="empty">没有数据 — 请先运行 <code>python3 web/export.py</code> 生成 data/，再刷新本页</p>';
    return;
  }

  var idxByCode = {};
  INDEX.universities.forEach(function (u) { idxByCode[u.code] = u; });

  /* ---- 学校全量数据懒加载：<script> 注入（file:// 下 fetch 被拦，script 不会）---- */
  var pending = {};
  function loadUni(code, cb) {
    if (window.UNI_DATA && window.UNI_DATA[code]) { cb(window.UNI_DATA[code]); return; }
    if (pending[code]) { pending[code].push(cb); return; }
    pending[code] = [cb];
    var s = document.createElement("script");
    s.src = "data/" + code + ".js";
    s.onload = function () {
      var cbs = pending[code]; delete pending[code];
      cbs.forEach(function (fn) { fn(window.UNI_DATA[code]); });
    };
    s.onerror = function () {
      delete pending[code];
      app.innerHTML = '<p class="empty">数据文件 data/' + code +
        '.js 加载失败 — 请运行 <code>python3 web/export.py</code></p>';
    };
    document.head.appendChild(s);
  }

  // 每个视图的筛选状态（跨路由保留）
  var filterState = {};

  function parseHash() {
    var seg = (location.hash || "#/").replace(/^#\/?/, "").split("/").filter(Boolean);
    if (!seg.length) return { view: "overview" };
    if (seg[0] === "u" && seg[1] && idxByCode[seg[1]]) {
      var code = seg[1];
      if (seg[2] === "p" && seg[3]) return { view: "program", code: code, id: +seg[3] };
      if (seg[2] === "m" && seg[3]) return { view: "module", code: code, id: +seg[3] };
      if (seg[2] === "f" && seg[3] != null) return { view: "faculty", code: code, id: +seg[3] };
      if (seg[2] === "d" && seg[3] != null) return { view: "dept", code: code, id: +seg[3] };
      return { view: "university", code: code };
    }
    return { view: "overview" };
  }

  function crumbs(route, uni) {
    var parts = ['<a href="#/">总览</a>'];
    if (route.code) {
      var meta = idxByCode[route.code];
      parts.push('<a href="#/u/' + route.code + '">' + UI.esc(meta.name_zh || meta.name_en) + "</a>");
    }
    if (uni && route.view === "faculty") {
      var fac = (uni.faculties || []).filter(function (x) { return x.id === route.id; })[0];
      parts.push(fac ? UI.esc(fac.name_zh || fac.name_en) : "未归类");
    }
    if (uni && route.view === "dept") {
      var dept = (uni.faculties || []).filter(function (x) { return x.id === route.id; })[0];
      if (dept && dept.parent_id) {
        var pf = (uni.faculties || []).filter(function (x) { return x.id === dept.parent_id; })[0];
        if (pf) parts.push('<a href="#/u/' + route.code + '/f/' + pf.id + '">' +
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
    renderNav(route);
    if (route.view === "overview") {
      app.innerHTML = crumbs(route) + VIEWS.overview(INDEX);
      window.scrollTo(0, 0);
      bindEvents(route);
      return;
    }
    app.innerHTML = '<p class="empty">加载 ' +
      UI.esc(idxByCode[route.code].name_zh || route.code) + " 数据…</p>";
    loadUni(route.code, function (uni) {
      var cur = parseHash();   // 加载期间用户可能已经跳走
      if (cur.view !== route.view || cur.code !== route.code || cur.id !== route.id) return;
      var html = crumbs(route, uni);
      if (route.view === "university") {
        html += VIEWS.university(uni, null);
      } else if (route.view === "faculty") {
        var fk = route.code + "/f" + route.id;
        var f = filterState[fk] || (filterState[fk] = { level: "all", fac: "all", q: "" });
        html += VIEWS.faculty(uni, route.id, f);
      } else if (route.view === "dept") {
        var dk = route.code + "/d" + route.id;
        var fd = filterState[dk] || (filterState[dk] = { level: "all", fac: "all", q: "" });
        html += VIEWS.dept(uni, route.id, fd);
      } else if (route.view === "program") {
        var prog = uni.programs.filter(function (p) { return p.id === route.id; })[0];
        html += prog ? VIEWS.program(uni, prog) : '<p class="empty">专业不存在</p>';
      } else if (route.view === "module") {
        var mod = uni.modules[route.id];
        html += mod ? VIEWS.module(uni, mod) : '<p class="empty">课程不存在</p>';
      }
      app.innerHTML = html;
      if (route.view !== "faculty" && route.view !== "dept") window.scrollTo(0, 0);
      bindEvents(route, uni);
    });
  }

  function renderNav(route) {
    nav.innerHTML = '<a class="brand" href="#/">留学辅导课程库</a>' +
      '<a class="tab' + (route.view === "overview" ? " on" : "") + '" href="#/">总览</a>' +
      INDEX.universities.map(function (u) {
        var on = route.code === u.code;
        return '<a class="tab' + (on ? " on" : "") + '" href="#/u/' + u.code + '">' +
          UI.esc(u.name_zh || u.name_en) + "</a>";
      }).join("");
  }

  function bindEvents(route, uni) {
    app.querySelectorAll("tr.click[data-href]").forEach(function (tr) {
      tr.addEventListener("click", function () { location.hash = tr.dataset.href; });
      tr.tabIndex = 0;
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter") location.hash = tr.dataset.href;
      });
    });
    // 学院/系页筛选（改状态后原地重渲染，不动 hash）
    if (route.view === "faculty" || route.view === "dept") {
      var f = filterState[route.code + (route.view === "faculty" ? "/f" : "/d") + route.id];
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
          setTimeout(function () {   // 懒加载渲染是异步的，聚焦要等 DOM 回来
            window.scrollTo(0, scrollY);
            var again = app.querySelector('input[data-filter="q"]');
            if (again) { again.focus(); again.setSelectionRange(again.value.length, again.value.length); }
          }, 0);
        }, 200));
      }
    }
  }

  function debounce(fn, ms) {
    var t;
    return function () { clearTimeout(t); t = setTimeout(fn, ms); };
  }

  foot.innerHTML = "数据来源：study_abroad 数据库（本地 MySQL）· 导出于 " + UI.esc(INDEX.generated_at) +
    " · 更新流程：<code>./run.sh</code> 爬取并刷新";

  window.addEventListener("hashchange", render);
  render();
})();
