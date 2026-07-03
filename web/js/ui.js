/* ============================================================
   ui.js — 纯工具函数与文案映射（无状态）
   挂载到 window.UI；经典脚本加载，file:// 下可直接运行
   ============================================================ */
(function () {
  "use strict";

  var UI = {};

  UI.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  };

  /* ---- 文案映射 ---- */
  UI.LEVEL = { UG: "本科", PGT: "授课硕士", PGR: "研究型", foundation: "预科", other: "其他" };
  UI.AUD = { all: "全部申请者", international: "国际学生", home: "本土学生" };
  UI.DLTYPE = {
    equal_consideration: "UCAS 常规截止", application: "申请截止",
    deposit: "押金截止", round: "分轮截止", language_evidence: "语言证明", other: "其他"
  };
  UI.ETYPE = {
    welcome_week: ["迎新周", "teach"], teaching_period: ["教学期", "teach"],
    reading_week: ["阅读周", "rest"], exam_period: ["考试季", "exam"],
    resit_period: ["补考", "exam"], holiday: ["假期", "rest"],
    closure: ["闭校", "rest"], graduation: ["毕业典礼", "teach"], other: ["其他", "teach"]
  };
  UI.CONTENT_TYPE = {
    week_topic: "每周主题", reading: "阅读书单", lecture_note: "讲义要点",
    assignment: "作业/项目", past_paper: "往年考试", exam_tips: "备考经验",
    student_review: "学生评价", other: "其他"
  };
  UI.SOURCE = {
    official_public: "官网公开", official_gated: "官方·登录墙内",
    student: "学生提供", agent: "第三方资料", manual_other: "手动录入"
  };
  UI.MODTYPE = { core: "必修", optional: "选修", elective: "任选" };

  /* ---- 格式化 ---- */
  UI.money = function (v, cur) {
    if (v == null) return null;
    var sym = { GBP: "£", USD: "$", EUR: "€", CNY: "¥", AUD: "A$", HKD: "HK$", SGD: "S$" }[cur] || (cur + " ");
    return sym + Number(v).toLocaleString("en-GB");
  };

  UI.dlStatus = function (iso) {
    var days = Math.ceil((new Date(iso) - new Date()) / 86400000);
    if (days < 0) return '<span class="tag past">已截止</span>';
    if (days <= 30) return '<span class="tag soon">还剩 ' + days + ' 天</span>';
    return '<span class="tag open">还剩 ' + days + ' 天</span>';
  };

  /** 专业的"最近有效截止"摘要（列表行用）：优先国际生未过期的 */
  UI.progDeadline = function (p) {
    var ds = (p.deadlines || []).slice().sort(function (a, b) {
      return a.deadline_at < b.deadline_at ? -1 : 1;
    });
    if (!ds.length) return { html: '<span class="tag past">无记录</span>', date: null };
    var now = new Date();
    var future = ds.filter(function (d) { return new Date(d.deadline_at) >= now; });
    var pick = future.length ? future[0] : ds[ds.length - 1];
    var lbl = (UI.AUD[pick.audience] || "").replace("学生", "");
    return {
      html: pick.deadline_at.slice(0, 10) + (lbl ? " <small>(" + lbl + ")</small> " : " ") + UI.dlStatus(pick.deadline_at),
      date: pick.deadline_at
    };
  };

  /** 考核占比条 */
  UI.assBar = function (ass) {
    if (!ass || !ass.length) return '<span class="asslabel">考核未公布</span>';
    var cls = function (t) {
      if (/exam/i.test(t)) return "a-exam";
      if (/course/i.test(t)) return "a-coursework";
      if (/group|class/i.test(t)) return "a-group";
      return "a-other";
    };
    var bar = ass.map(function (a) {
      return '<i class="' + cls(a.type) + '" style="width:' + a.weight + '%"></i>';
    }).join("");
    var lab = ass.map(function (a) { return a.weight + "% " + a.type; }).join(" + ");
    return '<span class="assbar">' + bar + '</span><span class="asslabel">' + UI.esc(lab) + '</span>';
  };

  UI.assLegend = '<div class="legend"><span><i class="a-exam"></i>考试</span>' +
    '<span><i class="a-coursework"></i>作业</span><span><i class="a-group"></i>小组/课堂</span>' +
    '<span><i class="a-other"></i>其他</span></div>';

  /** 来源可信度徽章 */
  UI.srcBadge = function (source, verified) {
    return '<span class="src ' + UI.esc(source) + '">' + (UI.SOURCE[source] || source) + '</span>' +
      (verified ? ' <span class="verified">✓ 已核实</span>' : ' <span class="unverified">未核实</span>');
  };

  window.UI = UI;
})();
