/* ============================================================
   views/calendar.js — 学期日历 section（学校页引用）
   ============================================================ */
(function () {
  "use strict";
  var UI = window.UI, esc = UI.esc;
  var VIEWS = window.VIEWS = window.VIEWS || {};

  VIEWS._calendarSection = function (uni) {
    if (!uni.calendar.length) {
      return "<section><h2>学期日历</h2>" +
        '<p class="empty">校历未采集（官网未公布或来源页尚未解析）</p></section>';
    }
    // 只看今天之后的事项（辅导排班不需要历史）；区间事件以结束日为准，
    // 进行中的（已开始未结束）保留
    var today = new Date().toISOString().slice(0, 10);
    var byYear = {};
    uni.calendar.forEach(function (e) {
      if ((e.end_date || e.start_date) < today) return;
      (byYear[e.academic_year] = byYear[e.academic_year] || []).push(e);
    });
    if (!Object.keys(byYear).length) {
      return "<section><h2>学期日历</h2>" +
        '<p class="empty">暂无今天之后的校历事项（数据可能待更新）</p></section>';
    }
    // 只显示当前学年和下一学年（更远的先留在库里）。
    // 学年制按地区分支：英港 = 9 月起算、标签 "2026/27"；
    // 澳洲 = 自然年制（2 月开学）、标签就是年份 "2026"
    var now = new Date(), wanted;
    if ((uni.country || "UK") === "AU") {
      wanted = [String(now.getFullYear()), String(now.getFullYear() + 1)];
    } else {
      var sy = now.getMonth() + 1 >= 9 ? now.getFullYear() : now.getFullYear() - 1;
      wanted = [sy, sy + 1].map(function (y) {
        return y + "/" + String((y + 1) % 100).padStart(2, "0");
      });
    }
    var years = Object.keys(byYear).filter(function (y) { return wanted.indexOf(y) >= 0; });
    if (!years.length) years = Object.keys(byYear);   // 全不匹配时兜底全显示
    var h = "<section><h2>学期日历</h2>";
    years.sort().forEach(function (y, yi) {
      // 每学年一个折叠栏：当前学年默认展开，下一学年收起（校历越攒越长）
      h += '<details data-fold="cal-' + esc(y) + '"' + (yi === 0 ? " open" : "") + "><summary>" + esc(y) +
        " 学年 <span class='sub'>（" + byYear[y].length + " 项）</span></summary>" +
        '<div class="scroll"><table><tr><th>起</th><th>止</th><th>事项</th><th>类型</th></tr>';
      var TRACK = { ioe: "教育学院轨", pharmacy: "药学院轨", medicine: "医学院轨" };
      byYear[y].forEach(function (e) {
        var t = UI.ETYPE[e.event_type] || [e.event_type, "teach"];
        var trk = (e.calendar_track && e.calendar_track !== "standard")
          ? ' <span class="sub">（' + esc(TRACK[e.calendar_track] || e.calendar_track) + '）</span>' : "";
        var nm = e.name_zh ? esc(e.name_zh) + " <span class='sub'>" + esc(e.name) + "</span>"
                           : esc(e.name);
        h += "<tr><td class='date'>" + e.start_date + "</td><td class='date'>" + (e.end_date || "—") +
          "</td><td>" + nm + trk + "</td><td><span class='etype " + t[1] + "'>" + t[0] + "</span></td></tr>";
      });
      h += "</table></div></details>";
    });
    return h + "</section>";
  };
})();
