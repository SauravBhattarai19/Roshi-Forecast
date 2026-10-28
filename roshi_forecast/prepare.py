# -*- coding: utf-8 -*-
"""
prepare.py — ``roshi-forecast setup``: everything a site needs before its first
cycle, done once (with Earth Engine, when the model settings use it).

1. **Terrain** — the ``process_dem`` stage into ``static/``.
2. **Soil date** — the soil-moisture layer (SERVES) is picked by the date of
   ``EVENT_START_UTC``; a forecast keeps one, so setup writes today's date into
   the model settings if it has none.  Every cycle then loads the same soil,
   which the restart check requires.
3. **Layers** — the model is started once normally, so every Earth Engine
   layer (land cover, Ksat, soil texture, deficit, HydroATLAS, …) is saved in
   ``static/``, and once more with Earth Engine switched off.  The two must
   give the same parameters; if not, the message names the one that still
   needs Earth Engine.
4. **Warm-up** — ``warm_up_days`` of past rain (station archive, filled from the
   main forecast model's own past) from dry, which saves the first state.
5. **Flood-area DEMs** — each area's map is drawn once from the warm-up, which
   downloads and keeps its DEM in ``static/areas/<area>/``; the basin map's
   boxes likewise in ``static/basin_map/`` (basinmap.py).
"""

import contextlib
import io
import os
from datetime import timedelta

import pandas as pd

from .cycle import (Context, Status, _catch_up, floor_hour, model_config,
                    observation_time, read_inflows, read_stations, utcnow)
from .offline import earth_engine_blocked
from .sitefile import slug


class SetupError(RuntimeError):
    pass


def pin_soil_date(site, today, log=print):
    """Write EVENT_START_UTC (the soil date) into the model settings if missing."""
    cfg = model_config(site)
    if cfg.EVENT_START_UTC:
        log(f"  Soil date: {str(cfg.EVENT_START_UTC).split()[0]} (EVENT_START_UTC in "
            f"{os.path.basename(site.model)}); every cycle uses it.")
        return str(cfg.EVENT_START_UTC)
    if not site.model.endswith((".yaml", ".yml")):
        raise SetupError(f"Set EVENT_START_UTC in {site.model}: the date of the soil "
                         "moisture every cycle uses (e.g. today).")
    value = today.strftime("%Y-%m-%d 00:00")
    with open(site.model, "a") as f:
        f.write(f"\n# Added by 'roshi-forecast setup': the date of the soil-moisture layer\n"
                f"# every forecast cycle uses (the run times come from the forecast).\n"
                f"EVENT_START_UTC: '{value}'\n")
    log(f"  Soil date: {value[:10]} written into {site.model} as EVENT_START_UTC.")
    return value


def _dummy_rain(static_dir, cfg):
    """Zero rain at the basin centre, so the model can be started for the checks."""
    from pyproj import Transformer
    from MRRpy.core.io_utils import routing_grid_crs
    from .sources import basin_centre
    lat, lon = basin_centre(cfg)
    e, n = Transformer.from_crs("EPSG:4326", routing_grid_crs(cfg), always_xy=True) \
        .transform(lon, lat)
    d = os.path.join(static_dir, "..", "setup_check")
    os.makedirs(d, exist_ok=True)
    g, t = os.path.join(d, "gauges.csv"), os.path.join(d, "timeseries.csv")
    pd.DataFrame({"gauge_id": ["G1"], "name": ["centre"], "easting_m": [e],
                  "northing_m": [n]}).to_csv(g, index=False)
    pd.DataFrame({"time_s": [0, 3600], "G1": [0.0, 0.0]}).to_csv(t, index=False)
    return g, t


def check_layers(site, log=print):
    """Start the model with and without Earth Engine; their parameters must match."""
    from MRRpy.core.routing import restart, router

    def start(blocked):
        cfg = model_config(site)
        cfg.PRECIP_METHOD = "idw"
        cfg.PRECIP_GAUGE_FILE, cfg.PRECIP_TIMESERIES_FILE = _dummy_rain(site.dir("static"), cfg)
        cfg.TOTAL_SIMULATION_TIME_HOURS = 1.0
        buf = io.StringIO()
        ctx = earth_engine_blocked() if blocked else contextlib.nullcontext()
        try:
            with ctx, contextlib.redirect_stdout(buf):
                grid = router.initialise_grid(cfg)
        except Exception as exc:
            tail = "\n".join(buf.getvalue().splitlines()[-8:])
            raise SetupError(("With Earth Engine off, the model" if blocked else "The model")
                             + f" could not start: {exc}\n{tail}") from None
        warns = [ln.strip() for ln in buf.getvalue().splitlines() if "[WARN]" in ln]
        return restart.describe(grid, cfg, cfg.ROUTING_SCHEME), warns

    log("  Starting the model once to save its layers …")
    normal, warns = start(False)
    for w in warns:
        log(f"    {w}")
    log("  … and once with Earth Engine off, to check nothing is missing.")
    offline, _ = start(True)
    try:
        restart._check(normal, offline, "(Earth Engine off)")
    except restart.RestartError as exc:
        msg = str(exc).replace("The state file (Earth Engine off) does not fit this model:",
                               "With Earth Engine off,")
        raise SetupError(msg + " That layer still needs Earth Engine at every run: set its "
                         "source in the model settings to a saved file (raster) or a plain "
                         "value.") from None
    log("  Layers: all saved; the model starts the same with Earth Engine off.")
    return normal


def warm_up(site, now=None, days=None, log=print, parallel=True, record_flood=True):
    """Run *days* of past rain from dry up to the last report → the first state."""
    from MRRpy.core.io_utils import routing_grid_crs
    now = (now or utcnow()).replace(second=0, microsecond=0)
    days = site.warm_up_days if days is None else days
    cfg = model_config(site)
    status = Status(now)
    ctx = Context(now=now, cfg=cfg, cache_dir=site.dir("forecasts_cache"), log=log)
    stations = read_stations(site, ctx, status, log)
    t_obs, active = observation_time(stations, now, site.station_silent_minutes)
    stations = [s for s in stations if s[0] in active] if active else stations
    until = floor_hour(t_obs)
    start = floor_hour(until - timedelta(days=float(days)))
    if until <= start:
        raise SetupError("warm_up_days must be more than 0.")
    inflows = read_inflows(site, ctx, status, log)
    log(f"  Warm-up: {days:g} days of past rain, {start:%Y-%m-%d %H:%M} → "
        f"{until:%Y-%m-%d %H:%M} UTC, from dry …")
    t, path = _catch_up(site, ctx, stations, inflows, start, None, until, t_obs,
                        routing_grid_crs(cfg), site.dir("cycles", "warm_up"), status, log,
                        parallel, record_flood=record_flood, name="warm_up")
    log(f"  Warm-up done: first state {os.path.basename(path)}")
    return t, path, site.dir("cycles", "warm_up", "warm_up")


def area_dems(site, run_dir, log=print):
    """Draw each area once from *run_dir* (Earth Engine on), keeping its DEM."""
    from MRRpy.config import Config
    from MRRpy.core.inundation import make_flood_maps
    for area in site.flood_areas:
        cfg = model_config(site, run_dir)
        cfg.INUNDATION_AREA = list(area.box)
        cfg.INUNDATION_METHOD = area.method
        if area.dem.lower().endswith((".tif", ".tiff")):
            cfg.INUNDATION_DEM, cfg.INUNDATION_DEM_PATH = "file", area.dem
        else:
            cfg.INUNDATION_DEM = area.dem
        if area.dem_scale_m:
            cfg.INUNDATION_DEM_SCALE_M = area.dem_scale_m
        cfg.INUNDATION_ANIMATION = False
        lines = []
        make_flood_maps(Config.from_dict(cfg.to_dict()), log=lines.append,
                        out_dir=os.path.join(run_dir, "areas", slug(area.name)),
                        cache_dir=site.dir("static", "areas", slug(area.name)))
        grid_line = next((ln for ln in lines if "Flood maps" in ln), "")
        log(f"  Flood area {area.name}: ready{(' — ' + grid_line.split('|')[-1].strip()) if grid_line else ''}")


def map_dems(site, run_dir, log=print):
    """Every flood map's DEM: the areas', and the basin map's boxes."""
    if site.flood_areas:
        area_dems(site, run_dir, log)
    if site.basin_map:
        from . import basinmap
        basinmap.prepare(site, run_dir, model_config(site, run_dir), log)


def latest_flood_run(site):
    """The newest run folder with recorded flows (a cycle's main version, or the warm-up)."""
    import glob
    found = glob.glob(site.dir("cycles", "*", "*", "inundation", "network.npz"))
    if not found:
        raise SetupError("no run has recorded the river flows yet: run "
                         "'roshi-forecast setup' (with the warm-up) first")
    return os.path.dirname(os.path.dirname(max(found, key=os.path.getmtime)))


def setup_site(site, now=None, log=print, force_terrain=False, warm=True, parallel=True):
    """Prepare *site* once (see the module docstring) → summary dict."""
    from MRRpy.pipeline import run_pipeline
    now = (now or utcnow()).replace(second=0, microsecond=0)
    for d in ("static", "archive", "states", "cycles", "site"):
        os.makedirs(site.dir(d), exist_ok=True)
    log(f"Setting up '{site.name}' in {site.folder}")
    pin_soil_date(site, now, log)
    cfg = model_config(site)
    if force_terrain or not os.path.isfile(cfg.ROUTING_DEM_PATH):
        log("  Terrain: preparing the DEM, flow directions and the basin …")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_pipeline(cfg, stages=("process_dem",), on_log=lambda *_: None)
        log(f"  Terrain: done ({cfg.OUTPUT_DIR})")
    else:
        log("  Terrain: already prepared.")
    check_layers(site, log)
    out = {"static": site.dir("static")}
    if warm:
        t, path, run_dir = warm_up(site, now=now, log=log, parallel=parallel,
                                   record_flood=site.has_maps())
        out.update(first_state=path)
        map_dems(site, run_dir, log)
    log("Setup done. Next: roshi-forecast run -f " + os.path.relpath(site.path))
    return out
