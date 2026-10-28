/* Front page of several flood forecasts: reads places.json (places.py) and shows
   each place on a map and as a card, in words and a table. */
(function () {
  "use strict";
  var LEVEL = { danger: "above danger level", warning: "above warning level",
                normal: "below warning level" };

  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function getJSON(url) {
    return fetch(url + "?t=" + Date.now()).then(function (r) {
      if (!r.ok) throw new Error(url + ": " + r.status);
      return r.json();
    });
  }
  function fmt(iso, tz) {
    var d = new Date(iso.replace("Z", ":00Z"));
    try {
      return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric",
        month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
        timeZone: tz || "UTC" }).format(d);
    } catch (e) { return iso; }
  }
  function q(x) {
    if (x === null || x === undefined) return "–";
    return (x >= 100 ? Math.round(x).toLocaleString("en-GB") : x >= 10 ? x.toFixed(1) : x.toFixed(2));
  }
  function levelText(p) {
    if (p.level) return LEVEL[p.level];
    return p.has_levels ? "–" : "no levels set yet";
  }
  function pageOf(c) { return c.id + "/index.html"; }

  function card(c) {
    var box = el("article", { "class": "place", "aria-labelledby": "place-" + c.id });
    var h = el("h3", { id: "place-" + c.id });
    var a = el("a", { href: pageOf(c) }, c.name);
    h.appendChild(a);
    box.appendChild(h);
    if (!c.has_forecast) {
      box.appendChild(el("p", { "class": "state" }, "No forecast yet: the first update has not run."));
      return box;
    }
    var tz = c.timezone || "UTC";
    var state = el("p", { "class": "state" + (c.late ? " late" : "") });
    state.textContent = (c.late ? "Late: not updated since " : "Updated ") + fmt(c.cycle_utc, tz) +
      " (" + tz + "). Measured rain up to " + fmt(c.t_obs_utc, tz) + "; forecast " +
      c.forecast_hours + " hours ahead.";
    box.appendChild(state);
    if (c.rain_next_mm !== null && c.rain_next_mm !== undefined) {
      box.appendChild(el("p", {}, "Rain expected over the basin in the next " + c.forecast_hours +
        " hours (" + c.main + "): " + Math.round(c.rain_next_mm) + " mm."));
    }
    var t = el("table"), cap = el("caption", {}, "Highest river flow expected at each point");
    t.appendChild(cap);
    var hr = el("tr");
    ["Point", "Highest flow (" + c.main + ")", "Around", "All forecasts", "Level"].forEach(
      function (x) { hr.appendChild(el("th", { scope: "col" }, x)); });
    t.appendChild(hr);
    c.points.forEach(function (p) {
      var r = el("tr");
      r.appendChild(el("th", { scope: "row" }, p.name));
      r.appendChild(el("td", { "class": "num" }, q(p.main_q) + " m³/s"));
      r.appendChild(el("td", {}, p.main_utc ? fmt(p.main_utc, tz) : "–"));
      r.appendChild(el("td", { "class": "num" },
        p.low_q === null ? "–" : q(p.low_q) + " – " + q(p.high_q) + " m³/s"));
      var lv = el("td");
      var tag = el("span", { "class": "level " + (p.level || "none") }, levelText(p));
      lv.appendChild(tag);
      r.appendChild(lv);
      t.appendChild(r);
    });
    var wrap = el("div", { "class": "tablewrap" });
    wrap.appendChild(t);
    box.appendChild(wrap);
    var more = el("p");
    more.appendChild(el("a", { href: pageOf(c) }, "Open the " + c.name + " forecast: charts, flood maps and rain"));
    box.appendChild(more);
    return box;
  }

  function drawMap(places) {
    if (typeof L === "undefined") { $("map").hidden = true; return; }
    var map = L.map("map", { zoomSnap: 0.25, scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18,
      attribution: "© OpenStreetMap contributors" }).addTo(map);
    var all = L.featureGroup().addTo(map);
    var colour = getComputedStyle(document.documentElement).getPropertyValue("--s1").trim();
    var done = places.map(function (c) {
      return getJSON(c.id + "/data/basin.geojson").then(function (g) {
        var layer = L.geoJSON(g, { style: { color: colour, weight: 2, fillOpacity: 0.12 } });
        layer.bindTooltip(c.name, { permanent: true, direction: "center", className: "place-label" });
        layer.on("click", function () { window.location.href = pageOf(c); });
        layer.addTo(all);
      }).catch(function () {});
    });
    Promise.all(done).then(function () {
      if (all.getLayers().length) map.fitBounds(all.getBounds(), { padding: [20, 20] });
      else map.setView([28.2, 84.1], 6.5);                      // Nepal
    });
  }

  getJSON("places.json").then(function (d) {
    document.title = d.title; $("title").textContent = d.title;
    if (d.notice) $("notice").appendChild(document.createTextNode(" " + d.notice));
    var n = d.places.length;
    $("updated").textContent = n + (n === 1 ? " place" : " places") + ". This page was made " +
      fmt(d.built_utc, d.places.length ? d.places[0].timezone : "UTC") + ".";
    var list = $("places");
    d.places.forEach(function (c) { list.appendChild(card(c)); });
    drawMap(d.places.filter(function (c) { return c.has_forecast; }));
  }).catch(function () {
    $("updated").textContent = "No places have been published here yet.";
  });
})();
