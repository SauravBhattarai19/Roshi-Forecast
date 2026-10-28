# -*- coding: utf-8 -*-
"""
products.py — what the web page shows, as plain files under ``site/data`` and
``site/maps``.

    data/latest.json            the cycle: times, versions, stations, points with
                                their highest expected flow and level, areas
    data/points/<point>.json    flow at the point for every version (UTC times)
    data/points/<point>.csv     the same as a table, for download
    data/rain.json, rain.csv    basin-average rain per hour for every version
    data/basin.geojson          the modelled basin outline
    maps/<area>/depth.png       deepest water, on the web map's projection
    maps/<area>/depth.json      its corners and the depth classes
    maps/<area>/extent.geojson  the flooded outline
    maps/<area>/flood_depth_max.tif   the depth map itself, for GIS

Levels are given in words and in the tables, never by colour alone.
"""

import json
import os
import shutil
from datetime import timedelta

import numpy as np
import pandas as pd

from .sitefile import NO_RAIN, slug

DEPTH_CLASSES = [(0.1, 0.5, "#c6dbef"), (0.5, 1.0, "#6baed6"), (1.0, 2.0, "#2171b5"),
                 (2.0, 3.0, "#08519c"), (3.0, np.inf, "#08306b")]


def _iso(t):
    return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%MZ")


def _write_json(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"), default=str)
    os.replace(tmp, path)


def level(q, point):
    """'danger' | 'warning' | 'normal' | None (no levels set) for flow *q*."""
    if point.warning_m3s is None and point.danger_m3s is None:
        return None
    if point.danger_m3s is not None and q >= point.danger_m3s:
        return "danger"
    if point.warning_m3s is not None and q >= point.warning_m3s:
        return "warning"
    return "normal"


LEVEL_WORDS = {"danger": "above danger level", "warning": "above warning level",
               "normal": "below warning level", None: ""}


def _flows(vdir, run_start, gauge):
    """Flow series [m³/s] at a gauge column (or the outlet) of one version run."""
    if gauge is None:
        df = pd.read_csv(os.path.join(vdir, "hydrograph.csv"))
        q = df["Q_m3s"]
    else:
        df = pd.read_csv(os.path.join(vdir, "gauges.csv"))
        q = df[f"{gauge}_Q_m3s"]
    t = pd.DatetimeIndex([run_start + timedelta(seconds=float(s)) for s in df["time_s"]])
    return pd.Series(q.to_numpy(float), index=t)


def _point_list(site):
    from .sitefile import Point
    pts = [(slug(p.name), p, slug(p.name)) for p in site.hydrograph_points]
    if "outlet" not in [k for k, _, _ in pts]:
        pts.append(("outlet", Point("Outlet (end of the model)", 0.0, 0.0), None))
    return pts


def build(site, status, versions, main, run_start, t_obs, now):
    """Write the data files of a finished cycle (see the module docstring)."""
    data_dir = site.dir("site", "data")
    os.makedirs(os.path.join(data_dir, "points"), exist_ok=True)
    tz = site.display_timezone
    points_out = []
    for pid, point, gauge in _point_list(site):
        series = {}
        for v, info in versions.items():
            try:
                series[v] = _flows(info["dir"], run_start, gauge)
            except (OSError, KeyError):
                continue
        if not series:
            continue
        times = series[main].index if main in series else next(iter(series.values())).index
        table = pd.DataFrame({v: s.reindex(times) for v, s in series.items()})
        ahead = table[table.index > t_obs]
        peaks = {}
        for v in table:
            col = ahead[v].dropna()
            if len(col):
                peaks[v] = {"q": round(float(col.max()), 3), "utc": _iso(col.idxmax()),
                            "level": level(float(col.max()), point)}
        now_q = table[main].loc[:t_obs].dropna() if main in table else pd.Series(dtype=float)
        info = {"id": pid, "name": point.name, "lat": point.lat if gauge else None,
                "lon": point.lon if gauge else None, "warning_m3s": point.warning_m3s,
                "danger_m3s": point.danger_m3s, "peaks": peaks,
                "now_q": round(float(now_q.iloc[-1]), 3) if len(now_q) else None,
                "level": peaks.get(main, {}).get("level")}
        points_out.append(info)
        _write_json(dict(info, times=[_iso(t) for t in table.index], observed_until=_iso(t_obs),
                         series={v: [None if not np.isfinite(x) else round(float(x), 3)
                                     for x in table[v]] for v in table}),
                    os.path.join(data_dir, "points", f"{pid}.json"))
        csv = table.copy()
        csv.insert(0, "part", np.where(csv.index <= t_obs, "with station rain", "forecast"))
        csv.index.name = "time_utc"
        csv.round(3).to_csv(os.path.join(data_dir, "points", f"{pid}.csv"))

    rain = pd.DataFrame({v: info["mean_mm"] for v, info in versions.items()})
    est = versions[main]["estimated"] if main in versions else np.zeros(len(rain), bool)
    hourly = rain.resample("1h", label="right", closed="right").sum()
    est_h = pd.Series(est, index=rain.index).resample("1h", label="right",
                                                      closed="right").max().astype(bool)
    _write_json({"times": [_iso(t) for t in hourly.index], "observed_until": _iso(t_obs),
                 "estimated": [bool(x) for x in est_h.reindex(hourly.index).fillna(False)],
                 "series": {v: [round(float(x), 2) for x in hourly[v]] for v in hourly}},
                os.path.join(data_dir, "rain.json"))
    out = hourly.round(2)
    out.insert(0, "part", np.where(out.index <= t_obs, "station rain", "forecast"))
    out.index.name = "hour_ending_utc"
    out.to_csv(os.path.join(data_dir, "rain.csv"))
    past = rain[(rain.index > t_obs - timedelta(hours=site.look_back_hours))
                & (rain.index <= t_obs)]
    rain_summary = {"past_hours": site.look_back_hours,
                    "past_mm": round(float(past[main].sum()), 1) if main in past else None,
                    "next_24h_mm": {v: round(float(rain[v][(rain.index > t_obs) & (
                        rain.index <= t_obs + timedelta(hours=24))].sum()), 1) for v in rain},
                    "next_mm": {v: round(float(rain[v][rain.index > t_obs].sum()), 1)
                                for v in rain}}

    areas_out = []
    for area in site.flood_areas:
        st = status.get("areas", {}).get(area.name, {})
        entry = {"id": slug(area.name), "name": area.name, "box": list(area.box),
                 "method": area.method, "ok": bool(st.get("ok"))}
        if st.get("ok"):
            try:
                entry.update(area_map(os.path.join(st["dir"], "flood_depth_max.tif"),
                                      os.path.join(st["dir"], "flood_extent_max.geojson"),
                                      site.dir("site", "maps", slug(area.name))))
            except Exception as exc:                          # noqa: BLE001
                entry.update(ok=False, error=f"map image: {exc}")
        else:
            entry["error"] = st.get("error")
        areas_out.append(entry)

    basin = site.dir("static", "watershed.geojson")
    if os.path.isfile(basin):
        import geopandas as gpd
        gpd.read_file(basin).to_crs(4326).to_file(os.path.join(data_dir, "basin.geojson"),
                                                  driver="GeoJSON")
    stations = [{"name": s, **v} for s, v in status.get("stations", {}).items()]
    from .archive import stations as kept
    pos = {m["entry"]: (m["lat"], m["lon"], m.get("last_report_utc"))
           for m, _ in kept(site).values()}
    for s in stations:
        if s["name"] in pos:
            s["lat"], s["lon"], s["last_report_utc"] = pos[s["name"]]

    versions_out = []
    for v in site.versions():
        fc = status.get("forecasts", {}).get(v, {})
        run = status.get("versions", {}).get(v, {})
        versions_out.append({"name": v, "ran": bool(run.get("ok")), "main": v == main,
                             "issued_utc": fc.get("issued_utc"),
                             "note": ("no more rain after the last station report"
                                      if v == NO_RAIN else
                                      ("forecast feed failed; last good forecast used"
                                       if fc.get("reused") else fc.get("error", ""))),
                             "info": fc.get("info", {})})
    latest = {"title": site.website.get("title", site.name), "name": site.name,
              "notice": site.website.get("notice"), "links": site.website.get("links") or [],
              "display_timezone": tz, "cycle_utc": _iso(now), "t_obs_utc": _iso(t_obs),
              "run_start_utc": _iso(run_start), "forecast_hours": site.forecast_hours,
              "main": main, "versions": versions_out, "points": points_out,
              "areas": areas_out, "stations": stations, "rain": rain_summary,
              "estimated_past_rain": bool(np.any(est[np.asarray(rain.index <= t_obs)]))
              if len(rain) else False,
              "attribution": sorted({str(f.get("info", {}).get("attribution"))
                                     for f in status.get("forecasts", {}).values()
                                     if f.get("info", {}).get("attribution")})}
    _write_json(latest, os.path.join(data_dir, "latest.json"))
    return latest


def area_map(depth_tif, extent_geojson, out_dir):
    """depth.png on Web Mercator + depth.json (corners, classes) + extent → dict."""
    import rasterio
    from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
    from PIL import Image

    os.makedirs(out_dir, exist_ok=True)
    with rasterio.open(depth_tif) as src:
        dst_crs = "EPSG:3857"
        tr, w, h = calculate_default_transform(src.crs, dst_crs, src.width, src.height,
                                               *src.bounds)
        depth = np.full((h, w), np.nan, dtype="float32")
        reproject(rasterio.band(src, 1), depth, src_nodata=src.nodata, dst_transform=tr,
                  dst_crs=dst_crs, dst_nodata=np.nan, resampling=Resampling.nearest)
        bounds = transform_bounds(dst_crs, "EPSG:4326",
                                  tr.c, tr.f + tr.e * h, tr.c + tr.a * w, tr.f)
        shutil.copyfile(depth_tif, os.path.join(out_dir, "flood_depth_max.tif"))
        cell_km2 = abs(src.transform.a * src.transform.e) / 1e6
        with rasterio.open(depth_tif) as s2:
            raw = s2.read(1, masked=True).filled(np.nan)
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    classes = []
    for lo, hi, colour in DEPTH_CLASSES:
        m = (depth >= lo) & (depth < hi)
        r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
        rgba[m] = (r, g, b, 210)
        n = int(np.sum((raw >= lo) & (raw < hi)))
        classes.append({"from_m": lo, "to_m": None if np.isinf(hi) else hi, "colour": colour,
                        "area_km2": round(n * cell_km2, 3)})
    Image.fromarray(rgba, "RGBA").save(os.path.join(out_dir, "depth.png"), optimize=True)
    wet = raw[np.isfinite(raw) & (raw >= DEPTH_CLASSES[0][0])]
    info = {"bounds": [[bounds[1], bounds[0]], [bounds[3], bounds[2]]],  # [[S, W], [N, E]]
            "classes": classes, "max_depth_m": round(float(wet.max()), 2) if wet.size else 0.0,
            "flooded_km2": round(float(wet.size * cell_km2), 3)}
    _write_json(info, os.path.join(out_dir, "depth.json"))
    if os.path.isfile(extent_geojson):
        import geopandas as gpd
        g = gpd.read_file(extent_geojson)
        dst = os.path.join(out_dir, "extent.geojson")
        if len(g):
            g.to_crs(4326).to_file(dst, driver="GeoJSON")
        else:
            with open(dst, "w") as f:
                json.dump({"type": "FeatureCollection", "features": []}, f)
    rel = os.path.basename(out_dir)
    return dict(info, png=f"maps/{rel}/depth.png", extent=f"maps/{rel}/extent.geojson",
                tif=f"maps/{rel}/flood_depth_max.tif")
