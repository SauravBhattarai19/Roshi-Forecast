/* MRRpy flood forecast page: reads data/*.json and draws the summary, map,
   hydrograph charts (SVG, each forecast with its own line style) and tables. */
(function () {
  "use strict";
  var STYLES = [
    { colour: "var(--s1)", dash: "", width: 3 },
    { colour: "var(--s2)", dash: "8 4", width: 2 },
    { colour: "var(--s3)", dash: "2 3", width: 2 },
    { colour: "var(--s4)", dash: "10 3 2 3", width: 2 },
    { colour: "var(--s5)", dash: "1 4", width: 2 }
  ];
  var LEVEL = { danger: "above danger level", warning: "above warning level",
                normal: "below warning level" };
  var data, tz;

  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function svg(tag, attrs) {
    var e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }
  function getJSON(url) {
    return fetch(url + "?t=" + Date.now()).then(function (r) {
      if (!r.ok) throw new Error(url + ": " + r.status);
      return r.json();
    });
  }
  function fmt(iso, withDay) {
    var d = new Date(iso.replace("Z", ":00Z"));
    var o = { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: tz };
    if (withDay) { o.weekday = "short"; o.day = "numeric"; o.month = "short"; }
    try { return new Intl.DateTimeFormat("en-GB", o).format(d); }
    catch (e) { return iso; }
  }
  function q(x) { return x === null || x === undefined ? "–" :
    (x >= 100 ? Math.round(x) : x >= 10 ? x.toFixed(1) : x.toFixed(2)); }
  function levelTag(lv) {
    if (!lv) return null;
    return el("span", { "class": "level " + lv }, LEVEL[lv]);
  }
  function styleOf(name) {
    var i = data.versions.map(function (v) { return v.name; }).indexOf(name);
    if (name === "No more rain") return STYLES[4];
    return STYLES[Math.max(0, i) % 4];
  }
  function keySwatch(name) {
    var s = styleOf(name), k = svg("svg", { width: 34, height: 12, "aria-hidden": "true" });
    k.appendChild(svg("line", { x1: 1, y1: 6, x2: 33, y2: 6, stroke: s.colour,
      "stroke-width": s.width, "stroke-dasharray": s.dash }));
    var span = el("span"); span.appendChild(k); span.appendChild(document.createTextNode(" " + name));
    return span;
  }

  /* ── Line chart (SVG) ──────────────────────────────────────────────── */
  // the display time zone's offset from UTC (ms) at time v
  function tzOffset(v) {
    var p = {};
    new Intl.DateTimeFormat("en-GB", { timeZone: tz, hourCycle: "h23", year: "numeric",
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
      .formatToParts(new Date(v)).forEach(function (x) { p[x.type] = +x.value; });
    return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) - Math.floor(v / 60e3) * 60e3;
  }

  function chart(times, series, opts) {
    var W = 900, H = 300, L = 56, R = 16, T = 14, B = 42;
    var t = times.map(function (s) { return Date.parse(s.replace("Z", ":00Z")); });
    var t0 = t[0], t1 = t[t.length - 1];
    var ymax = opts.ymin || 0;
    Object.keys(series).forEach(function (k) {
      series[k].forEach(function (y) { if (y !== null && y > ymax) ymax = y; });
    });
    (opts.thresholds || []).forEach(function (h) { if (h.value > ymax) ymax = h.value; });
    ymax = ymax <= 0 ? 1 : ymax * 1.1;
    function X(v) { return L + (v - t0) / (t1 - t0 || 1) * (W - L - R); }
    function Y(v) { return T + (1 - v / ymax) * (H - T - B); }
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img",
                         "aria-label": opts.label });
    var step = Math.pow(10, Math.floor(Math.log10(ymax / 4)));
    while (ymax / step > 6) step *= 2;
    for (var y = 0; y <= ymax; y += step) {
      s.appendChild(svg("line", { "class": "grid", x1: L, x2: W - R, y1: Y(y), y2: Y(y) }));
      var tx = svg("text", { x: L - 6, y: Y(y) + 4, "text-anchor": "end" });
      tx.textContent = q(y); s.appendChild(tx);
    }
    var yl = svg("text", { x: 12, y: T + (H - T - B) / 2, transform:
      "rotate(-90 12 " + (T + (H - T - B) / 2) + ")", "text-anchor": "middle" });
    yl.textContent = opts.unit; s.appendChild(yl);
    // ticks every 6 h of the page's own clock (00, 06, 12, 18 local), days at midnight
    var day = 6 * 3600e3, off = tzOffset(t0);
    for (var v = Math.ceil((t0 + off) / day) * day - off; v <= t1; v += day) {
      s.appendChild(svg("line", { "class": "grid", x1: X(v), x2: X(v), y1: T, y2: H - B }));
      var lb = svg("text", { x: X(v), y: H - B + 16, "text-anchor": "middle" });
      lb.textContent = fmt(new Date(v).toISOString().slice(0, 16) + "Z", false);
      s.appendChild(lb);
      if (new Date(v + off).getUTCHours() === 0 || v - day < t0) {
        var ld = svg("text", { x: X(v), y: H - B + 32, "text-anchor": "middle" });
        ld.textContent = fmt(new Date(v).toISOString().slice(0, 16) + "Z", true).split(",")[0];
        s.appendChild(ld);
      }
    }
    s.appendChild(svg("line", { "class": "axis", x1: L, x2: W - R, y1: H - B, y2: H - B }));
    (opts.thresholds || []).forEach(function (h) {
      s.appendChild(svg("line", { "class": "thr " + h.kind, x1: L, x2: W - R,
                                  y1: Y(h.value), y2: Y(h.value) }));
      var tt = svg("text", { x: W - R - 4, y: Y(h.value) - 4, "text-anchor": "end" });
      tt.textContent = h.label; s.appendChild(tt);
    });
    if (opts.now) {
      var xn = X(Date.parse(opts.now.replace("Z", ":00Z")));
      s.appendChild(svg("line", { "class": "now", x1: xn, x2: xn, y1: T, y2: H - B }));
      var tn = svg("text", { x: xn + 4, y: T + 10 });
      tn.textContent = "last station report"; s.appendChild(tn);
    }
    Object.keys(series).forEach(function (k) {
      var st = styleOf(k), d = "", pen = false;
      series[k].forEach(function (y, i) {
        if (y === null) { pen = false; return; }
        d += (pen ? "L" : "M") + X(t[i]).toFixed(1) + " " + Y(y).toFixed(1);
        pen = true;
      });
      s.appendChild(svg("path", { d: d, fill: "none", stroke: st.colour,
        "stroke-width": st.width, "stroke-dasharray": st.dash }));
    });
    var box = el("div", { "class": "chart" });
    box.appendChild(s);
    return box;
  }

  // a table in its own box that scrolls sideways on a narrow screen
  function boxed(t) {
    var w = el("div", { "class": "tablewrap" }); w.appendChild(t); return w;
  }

  function dataTable(times, series, unit, every) {
    var d = el("details"), sm = el("summary", {}, "Show the numbers as a table");
    d.appendChild(sm);
    var wrap = el("div", { "class": "scroll" }), tb = el("table");
    var head = el("tr"); head.appendChild(el("th", { scope: "col" }, "Time (" + tz + ")"));
    Object.keys(series).forEach(function (k) {
      head.appendChild(el("th", { scope: "col" }, k + " (" + unit + ")"));
    });
    tb.appendChild(head);
    for (var i = 0; i < times.length; i += every) {
      var tr = el("tr"); tr.appendChild(el("td", {}, fmt(times[i], true)));
      Object.keys(series).forEach(function (k) {
        tr.appendChild(el("td", { "class": "num" }, q(series[k][i])));
      });
      tb.appendChild(tr);
    }
    wrap.appendChild(tb); d.appendChild(wrap);
    return d;
  }

  /* ── Sections ──────────────────────────────────────────────────────── */
  function summary() {
    var ul = $("summary"); ul.innerHTML = "";
    data.points.forEach(function (p) {
      var pk = p.peaks[data.main], li = el("li");
      if (!pk) return;
      li.appendChild(el("strong", {}, p.name + ": "));
      li.appendChild(document.createTextNode("highest expected flow " + q(pk.q) +
        " m³/s around " + fmt(pk.utc, true) + " (" + data.main + " forecast)"));
      var lt = levelTag(pk.level); if (lt) { li.appendChild(document.createTextNode(" ")); li.appendChild(lt); }
      var others = Object.keys(p.peaks).filter(function (v) { return v !== data.main; })
        .map(function (v) { return v + " " + q(p.peaks[v].q); });
      if (others.length) li.appendChild(document.createTextNode(
        ". Other forecasts: " + others.join(", ") + " m³/s."));
      ul.appendChild(li);
    });
    var r = data.rain, li2 = el("li");
    li2.textContent = "Rain over the basin: " + (r.past_mm === null ? "–" : r.past_mm) +
      " mm in the last " + r.past_hours + " h" + (data.estimated_past_rain ?
      " (partly estimated: a station did not report)" : "") + "; next 24 h: " +
      Object.keys(r.next_24h_mm).map(function (v) {
        return v + " " + r.next_24h_mm[v] + " mm"; }).join(", ") + ".";
    ul.appendChild(li2);
  }

  var map, overlay;
  function drawMap() {
    if (typeof L === "undefined") { $("map").textContent = "The map could not load."; return; }
    map = L.map("map", { zoomSnap: 0.25 });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18,
      attribution: "© OpenStreetMap contributors" }).addTo(map);
    var group = L.featureGroup().addTo(map);
    getJSON("data/basin.geojson").then(function (g) {
      L.geoJSON(g, { style: { color: "#333", weight: 2, fill: false } }).addTo(group);
      map.fitBounds(group.getBounds(), { padding: [10, 10] });
    }).catch(function () {});
    data.stations.forEach(function (s) {
      if (s.lat === undefined) return;
      L.marker([s.lat, s.lon], { icon: L.divIcon({ className: "", html:
        '<div style="width:12px;height:12px;background:#222;border:2px solid #fff"></div>' }),
        title: "Rain station " + s.name }).bindPopup("Rain station <b>" + s.name +
        "</b><br>last report " + (s.last_report_utc ? fmt(s.last_report_utc.replace(" ", "T") + "Z", true) : "–"))
        .addTo(group);
    });
    data.points.forEach(function (p) {
      if (p.lat === null) return;
      var pk = p.peaks[data.main];
      L.circleMarker([p.lat, p.lon], { radius: 7, color: "#000", weight: 2,
        fillColor: "#fff", fillOpacity: 1 }).bindPopup("<b>" + p.name + "</b><br>" +
        (pk ? "highest expected " + q(pk.q) + " m³/s " + (LEVEL[pk.level] || "") : ""))
        .bindTooltip(p.name, { permanent: true, direction: "right" }).addTo(group);
    });
    data.areas.forEach(function (a) {
      var b = a.box;
      L.rectangle([[b[1], b[0]], [b[3], b[2]]], { color: "#000", weight: 1,
        dashArray: "4 4", fill: false }).bindTooltip(a.name).addTo(group);
      var o = el("option", { value: a.id }, a.name + (a.ok ? "" : " (no map this time)"));
      if (!a.ok) o.disabled = true;
      $("area-pick").appendChild(o);
    });
    if (!group.getLayers().length) map.setView([0, 0], 2);
    $("area-pick").addEventListener("change", function () { showArea(true); });
    $("opacity").addEventListener("input", function () {
      if (overlay) overlay.setOpacity(+this.value); });
    var first = data.areas.filter(function (a) { return a.ok; })[0];
    if (first) { $("area-pick").value = first.id; showArea(); }
  }
  function showArea(zoom) {        // the page opens on the whole basin
    if (overlay) { map.removeLayer(overlay); overlay = null; }
    var a = data.areas.filter(function (x) { return x.id === $("area-pick").value; })[0];
    var lg = $("legend"); lg.innerHTML = "";
    if (!a || !a.ok) return;
    overlay = L.imageOverlay(a.png + "?t=" + Date.now(), a.bounds,
      { opacity: +$("opacity").value, alt: "Deepest expected water in " + a.name }).addTo(map);
    if (zoom) map.fitBounds(a.bounds);
    lg.appendChild(el("span", {}, "Deepest water:"));
    a.classes.forEach(function (c) {
      var s = el("span"), sw = el("span", { "class": "swatch" });
      sw.style.background = c.colour; s.appendChild(sw);
      s.appendChild(document.createTextNode(c.from_m + (c.to_m ? "–" + c.to_m : "+") + " m"));
      lg.appendChild(s);
    });
  }

  function points() {
    var box = $("points"); box.innerHTML = "";
    data.points.forEach(function (p) {
      var card = el("div", { "class": "card" });
      card.appendChild(el("h3", {}, p.name));
      box.appendChild(card);
      getJSON("data/points/" + p.id + ".json").then(function (d) {
        var thr = [];
        if (p.warning_m3s !== null) thr.push({ value: p.warning_m3s, kind: "warning",
          label: "warning level " + q(p.warning_m3s) + " m³/s" });
        if (p.danger_m3s !== null) thr.push({ value: p.danger_m3s, kind: "danger",
          label: "danger level " + q(p.danger_m3s) + " m³/s" });
        var keys = el("div", { "class": "keys" });
        Object.keys(d.series).forEach(function (k) { keys.appendChild(keySwatch(k)); });
        card.appendChild(keys);
        card.appendChild(chart(d.times, d.series, { unit: "m³/s", now: d.observed_until,
          thresholds: thr, label: "River flow at " + p.name + " for each forecast" }));
        var pt = el("table"), hr = el("tr");
        ["Forecast", "Highest flow (m³/s)", "Around", "Level"].forEach(function (h) {
          hr.appendChild(el("th", { scope: "col" }, h)); });
        pt.appendChild(hr);
        Object.keys(p.peaks).forEach(function (v) {
          var r = el("tr"), pk = p.peaks[v];
          r.appendChild(el("td", {}, v));
          r.appendChild(el("td", { "class": "num" }, q(pk.q)));
          r.appendChild(el("td", {}, fmt(pk.utc, true)));
          var c = el("td"), lt = levelTag(pk.level);
          if (lt) c.appendChild(lt); else c.textContent = "no levels set";
          r.appendChild(c); pt.appendChild(r);
        });
        card.appendChild(boxed(pt));
        card.appendChild(dataTable(d.times, d.series, "m³/s", 6));
        card.appendChild(el("a", { href: "data/points/" + p.id + ".csv", download: "" },
          "Download the flows (CSV)"));
      }).catch(function (e) { card.appendChild(el("p", {}, "No data: " + e.message)); });
    });
  }

  function rain() {
    getJSON("data/rain.json").then(function (d) {
      var box = $("rain"); box.innerHTML = "";
      box.appendChild(el("p", { "class": "help" }, "Average rain over the basin in each hour" +
        " (mm). Before the last station report it is measured" +
        (d.estimated.some(Boolean) ? "; hours a station missed are estimated from the " +
          data.main + " forecast" : "") + "."));
      var keys = el("div", { "class": "keys" });
      Object.keys(d.series).forEach(function (k) { keys.appendChild(keySwatch(k)); });
      box.appendChild(keys);
      box.appendChild(chart(d.times, d.series, { unit: "mm per hour", now: d.observed_until,
        label: "Hourly rain over the basin for each forecast" }));
      box.appendChild(dataTable(d.times, d.series, "mm", 1));
      box.appendChild(el("a", { href: "data/rain.csv", download: "" }, "Download the rain (CSV)"));
    });
  }

  function areas() {
    var box = $("areas"); box.innerHTML = "";
    if (!data.areas.length) { box.textContent = "No flood areas are set."; return; }
    var t = el("table"), hr = el("tr");
    ["Area", "Deepest water (m)", "Flooded (km²)", "Area by depth", "Map file"].forEach(
      function (h) { hr.appendChild(el("th", { scope: "col" }, h)); });
    t.appendChild(hr);
    data.areas.forEach(function (a) {
      var r = el("tr");
      r.appendChild(el("td", {}, a.name));
      if (!a.ok) {
        var c = el("td", { colspan: 4 }, "No map this time" + (a.error ? ": " + a.error : ""));
        r.appendChild(c); t.appendChild(r); return;
      }
      r.appendChild(el("td", { "class": "num" }, a.max_depth_m.toFixed(1)));
      r.appendChild(el("td", { "class": "num" }, a.flooded_km2.toFixed(2)));
      r.appendChild(el("td", {}, a.classes.map(function (c) {
        return c.from_m + (c.to_m ? "–" + c.to_m : "+") + " m: " + c.area_km2 + " km²";
      }).join("; ")));
      var f = el("td"); f.appendChild(el("a", { href: a.tif, download: "" }, "GeoTIFF"));
      r.appendChild(f); t.appendChild(r);
    });
    box.appendChild(el("p", { "class": "help" }, "Deepest water expected in each area over " +
      "the whole run (the last hours of measured rain and the " + data.main + " forecast)."));
    box.appendChild(boxed(t));
  }

  function sources() {
    var box = $("sources"); box.innerHTML = "";
    var t = el("table"), hr = el("tr");
    ["Forecast", "Issued (" + tz + ")", "Ran", "Note"].forEach(function (h) {
      hr.appendChild(el("th", { scope: "col" }, h)); });
    t.appendChild(hr);
    data.versions.forEach(function (v) {
      var r = el("tr");
      r.appendChild(el("td", {}, v.name + (v.main ? " (main)" : "")));
      r.appendChild(el("td", {}, v.issued_utc ? fmt(v.issued_utc.replace(" ", "T") + "Z", true) : "–"));
      r.appendChild(el("td", {}, v.ran ? "yes" : "no"));
      r.appendChild(el("td", {}, v.note || ""));
      t.appendChild(r);
    });
    box.appendChild(boxed(t));
    var s = el("table"), h2 = el("tr");
    ["Rain station", "Last report (" + tz + ")", "Read this time"].forEach(function (h) {
      h2.appendChild(el("th", { scope: "col" }, h)); });
    s.appendChild(h2);
    data.stations.forEach(function (st) {
      var r = el("tr");
      r.appendChild(el("td", {}, st.name));
      r.appendChild(el("td", {}, st.last_report_utc ?
        fmt(st.last_report_utc.replace(" ", "T") + "Z", true) : "–"));
      r.appendChild(el("td", {}, st.ok ? "yes" : "no — " + (st.error || "")));
      s.appendChild(r);
    });
    if (data.stations.length) box.appendChild(boxed(s));
    if (data.attribution.length) {
      $("credits").appendChild(document.createTextNode(" " + data.attribution.join(". ") + "."));
    }
  }

  function stale(status) {
    var box = $("stale");
    if (status && status.ok === false) {
      box.hidden = false;
      box.textContent = "The latest cycle (" + fmt(status.cycle_utc.replace(" ", "T") + "Z", true) +
        ") failed, so this page still shows the forecast of " + fmt(data.cycle_utc, true) + ".";
    }
  }

  getJSON("data/latest.json").then(function (d) {
    data = d; tz = d.display_timezone || "UTC";
    document.title = d.title; $("title").textContent = d.title;
    if (d.notice) $("notice").appendChild(document.createTextNode(" " + d.notice));
    $("updated").textContent = "Updated " + fmt(d.cycle_utc, true) + " (" + tz +
      "). Measured rain up to " + fmt(d.t_obs_utc, true) + "; forecast " +
      d.forecast_hours + " hours ahead.";
    summary(); drawMap(); points(); rain(); areas(); sources();
    getJSON("data/status.json").then(stale).catch(function () {});
    getJSON("../places.json").then(function () { $("crumbs").hidden = false; })
      .catch(function () {});                       // only inside a site of several places
  }).catch(function () {
    $("updated").textContent = "No forecast has been published here yet.";
  });
})();
