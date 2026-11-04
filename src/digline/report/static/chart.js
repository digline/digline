// digline's one script (ADR 0061 §7): it hands uPlot the numbers a page
// already carries in a data block, and takes its colours from the sheet.
// Served from the server's own origin, so `script-src 'self'` admits it and
// nothing inline. Progressive: without it a page still reads, and the table
// beside the chart still says everything the chart draws.
//
// A page opts in with an element `#series-chart` and a data block
// `<script type="application/json" id="series-data">` holding
// {"setups": [...], "x": [...], "y": [[...], ...], "ymax": n, "label": "..."}.
(function () {
  "use strict";
  var holder = document.getElementById("series-chart");
  var source = document.getElementById("series-data");
  if (!holder || !source || typeof uPlot === "undefined") return;
  var data = JSON.parse(source.textContent);
  var css = getComputedStyle(document.documentElement);
  function token(name) {
    return css.getPropertyValue(name).trim();
  }
  var axis = token("--muted");
  var grid = token("--line");
  var hues = [token("--s1"), token("--s2"), token("--s3")];
  var series = [{}];
  data.setups.forEach(function (name, i) {
    var hue = hues[i % hues.length];
    series.push({
      label: name,
      stroke: hue,
      width: 0,
      paths: function () { return null; },
      points: { show: true, size: 9, fill: hue },
    });
  });
  function width() { return Math.max(320, holder.clientWidth); }
  var plot = new uPlot(
    {
      width: width(),
      height: 240,
      series: series,
      scales: { y: { range: [0, data.ymax] } },
      axes: [
        { stroke: axis, grid: { stroke: grid }, ticks: { stroke: grid } },
        { stroke: axis, grid: { stroke: grid }, ticks: { stroke: grid },
          label: data.label, labelSize: 20 },
      ],
      cursor: { points: { size: 11 } },
    },
    [data.x].concat(data.y),
    holder
  );
  window.addEventListener("resize", function () {
    plot.setSize({ width: width(), height: 240 });
  });
})();
