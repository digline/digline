// digline's one script (ADR 0061 §7), in two halves: (a) it hands uPlot the
// numbers a page already carries in a data block, and takes its colours from
// the sheet; (b) it keeps the command line under each form equal to the form.
// Served from the server's own origin, so `script-src 'self'` admits it and
// nothing inline. Progressive: without it a page still reads, the table
// beside the chart still says everything the chart draws, every form still
// writes, and the line under a form is the one the server served.
//
// (a) A page opts in with an element `#series-chart` and a data block
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

// (b) The command line under each form that writes, kept equal to the form's
// fields as they are edited (ADR 0061 §7). The server writes the line as the
// form is served, the base it starts from in `data-base`, and on each field
// the flag it fills in `data-flag`, with `data-value` where the word is not
// the field's own value. This script holds no flag of its own: it joins what
// the page names, quoted as `shlex.quote` quotes, so a line it writes is the
// line the server would have written for the same fields.
(function () {
  "use strict";
  function quote(word) {
    if (word === "") return "''";
    if (/^[A-Za-z0-9_@%+=:,.\/-]+$/.test(word)) return word;
    return "'" + word.replace(/'/g, "'\"'\"'") + "'";
  }
  function follow(form) {
    var line = form.querySelector("[data-base]");
    if (!line) return;
    function render() {
      var words = [line.getAttribute("data-base")];
      form.querySelectorAll("[data-flag]").forEach(function (field) {
        var chosen = field.type === "radio" || field.type === "checkbox";
        if (chosen ? !field.checked : field.value === "") return;
        words.push(field.getAttribute("data-flag"));
        var word = chosen ? field.getAttribute("data-value") : field.value;
        if (word !== null) words.push(quote(word));
      });
      line.textContent = words.join(" ");
    }
    form.addEventListener("input", render);
    form.addEventListener("change", render);
  }
  Array.prototype.forEach.call(document.querySelectorAll("form[data-writes]"), follow);
})();
