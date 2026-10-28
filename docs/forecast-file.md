# The forecast file

`forecast.yaml` lists what a [live forecast](how-it-works.md) reads, runs and shows.
`roshi-forecast new` writes a commented one. `roshi-forecast check` reports
every problem at once, in plain words. A misspelt key gets "did you mean".
Relative paths are read from the forecast file's folder, and times are UTC.

```yaml
name: Roshi Khola flood forecast
model: model.yaml
display_timezone: Asia/Kathmandu
forecast_hours: 48
rain_stations:
  - {name: AWS at Roshi, source: alertnepal, station: 496}
rain_forecasts:
  - {name: ECMWF, source: open_meteo, model: ecmwf_ifs025}
  - {name: GFS, source: open_meteo, model: gfs_seamless}
main_forecast: ECMWF
hydrograph_points:
  - {name: Panauti, lat: 27.5843, lon: 85.5185, warning_m3s: 150, danger_m3s: 300}
flood_areas:
  - {name: Panauti town, box: [85.505, 27.575, 85.530, 27.595], method: 2d}
website:
  title: Roshi Khola flood forecast (experimental)
```

## Main settings

| Key | Default | Meaning |
|---|---|---|
| `name` | Flood forecast | a title for the forecast |
| `model` | (needed) | the MRRpy settings file; its `OUTPUT_DIR` is not used: setup works in `static/` |
| `folder` | the forecast file's folder | where `static/`, `archive/`, `states/`, `cycles/` and `site/` go |
| `display_timezone` | UTC | times on the web page, e.g. `Asia/Kathmandu` |
| `every_minutes` | 30 | minutes between updates (`serve`) |
| `forecast_hours` | 48 | how far ahead each update forecasts |
| `look_back_hours` | 12 | hours of station rain each update runs again |
| `warm_up_days` | 30 | days of past rain setup runs to wet the soil |
| `missing_rain` | `forecast_model` | a 10-minute interval no station reported: the main forecast's rain, or `zero` |
| `station_silent_minutes` | 60 | a station silent this long counts as missing |
| `main_forecast` | the first forecast | the forecast that draws the flood maps |
| `no_rain_version` | true | also run a version with no more rain |
| `workers` | 0 | model runs at the same time (0 = all versions at once) |
| `threads_per_run` | 8 | CPU threads for each run |
| `keep_cycles_days` | 3 | days to keep each update's folder |
| `keep_states_days` | 30 | days to keep the daily saved states |

## Rain stations: `rain_stations`

Each entry has a `name`, a `source` and that source's keys.

Stations stand for the whole basin: the rain at each model cell is spread from
them by distance. List them only where they are spread well enough for that.
With `rain_stations: []`, the rain before now is the main forecast model's own
(`missing_rain`), and the page says so. The Roshi Khola does this: its three
stations all lie in the quarter of the basin above the Panauti gauge, which
runs on them as its own place (`places/panauti`).

| Source | Keys | Reads |
|---|---|---|
| `alertnepal` | `station` (number), `parameter` (`PCPN_10M`) | an automatic weather station of the [alertnepal](https://alertnepal.online) dashboard (Nepal). These are the dashboard's own interfaces, not a published API: ask the alertnepal team before you run a forecast on them |
| `rts` | `station` (number), `parameter` (`PCPN_10M`), `extra` (soil moisture), `backfill_days` (35), `sign_in` (`RTS`) | a station of the [RTS](https://rts.wscada.net) time-series system, which needs a sign-in: save it with `scripts/save-credentials.sh rts`. `python -m roshi_forecast.sources.rts` lists the stations it can read. The first reading goes back `backfill_days`, so the warm-up runs on measured rain; later ones ask only for what is new. Readings flagged by RTS's quality check are left out |
| `csv` | `path` (file or web address), `lat`, `lon`; `time_column` (`time_utc`), `value_column` (`rain_mm`), `timezone`, `step_minutes` | one gauge: the mm that fell in the interval ending at each time |
| `gauge_files` | `gauges`, `timeseries`, `start_utc`; `crs` | many gauges in MRRpy's own [rain-gauge files](https://mrrpy.readthedocs.io/en/latest/manual/precipitation/), e.g. satellite rain prepared for a rehearsal |

## Rain forecasts: `rain_forecasts`

Each forecast runs as its own version, with its own line on every chart.

| Source | Keys | Reads |
|---|---|---|
| `open_meteo` | `model`, e.g. `ecmwf_ifs025`, `gfs_seamless`, `icon_seamless`; `spacing_m` (10000), `buffer_m`; `api` (`forecast`, or `single_run` for a rehearsal), `run_hours`, `delay_hours` | a weather model through MRRpy's [Open-Meteo source](https://mrrpy.readthedocs.io/en/latest/manual/precipitation/): each model cell over the basin becomes a rain point. It is fetched again when its window moves, at most once an hour. At 10 km spacing that is about 25 points per model, well inside Open-Meteo's free 10,000 calls a day |
| | | For a rehearsal, Open-Meteo keeps past runs of only some models: the 2024 ECMWF runs are under `ecmwf_ifs` (9 km), not `ecmwf_ifs025` |
| `alertnepal_forecast` | `points`: `[[lat, lon], …]` (default: the middle of the basin) | alertnepal's hourly rain forecast (240 h). Its times are Nepal time marked as UTC, and are converted |
| `csv` | `path`, `lat`, `lon` (as the `csv` station) | a forecast at one point from a file |

## Inflows: `inflows`

These are rivers that enter the model at its edge, each an
[inflow hydrograph](https://mrrpy.readthedocs.io/en/latest/manual/inflows/).

| Key | Meaning |
|---|---|
| `name`, `lat`, `lon` | the point; it moves to the nearest river cell |
| `source: csv`, `path` | the readings: `time_utc` and `Q_m3s` |
| `ahead` | after the last reading: `hold` it, or `recede` |
| `recede_hours` | how fast it recedes: 24 h falls to 37 % in a day |

## Hydrograph points: `hydrograph_points`

| Key | Meaning |
|---|---|
| `name`, `lat`, `lon` | the point; it moves to the river cell of largest drainage within `snap_radius_cells` (2). A larger radius slides a point down its river, so put the point on the river and keep the radius small |
| `warning_m3s`, `danger_m3s` | optional levels. The page says "above warning level" or "above danger level" in words |

The outlet gets a hydrograph too, unless a point is already within 500 m of it.

## River gauges: `river_gauges`

A river gauge's measured water level, drawn in its own panel under a point's
hydrograph, with its own scale, so the forecast can be checked against the river.
The model never uses it. Each entry has a `name`, a `source`, that source's keys
and `point`: the name of the hydrograph point it is drawn under (put that point
at the gauge). The readings are kept in `archive/levels/`.

| Source | Keys | Reads |
|---|---|---|
| `rts` | `station` (number), `parameter` (`WTR_LVL`), `backfill_days` (35), `sign_in` (`RTS`) | a river gauge of the RTS system (471 is the Roshi Khola at Panauti) |
| `csv` | `path` (file or web address); `time_column` (`time_utc`), `value_column` (`level_m`), `timezone` | the water level at each time |

The page shows the gauge's own reading, in metres. It is not the depth: the
RTS gauge at Panauti reads about 1342.7 m at low flow. It also says how far the
level is above its lowest reading of the last 30 days, and how it changed in
the last hour.

```text
hydrograph_points:
  - {name: Panauti gauge (RTS 471), lat: 27.56998, lon: 85.53894, snap_radius_cells: 3}
river_gauges:
  - {name: Roshi Khola at Panauti, source: rts, station: 471, point: Panauti gauge (RTS 471)}
```

## Flood areas: `flood_areas`

| Key | Meaning |
|---|---|
| `name` | the area's name |
| `box` | `[west, south, east, north]` in degrees |
| `method` | `hand` (seconds) or `2d` (more exact, about a minute): see [6.3](https://mrrpy.readthedocs.io/en/latest/manual/outputs/#63-flood-depth-and-extent-maps) |
| `dem` | `auto`, `model_grid`, a DEM name or a GeoTIFF, as `INUNDATION_DEM` |
| `dem_scale_m` | the resolution of a downloaded DEM |

## The web page: `website`

| Key | Meaning |
|---|---|
| `title` | the page title |
| `notice` | a line added to the notice at the top, e.g. who runs it |
| `publish` | `{git: {remote: …}}` pushes to GitHub Pages ([how](how-it-works.md#publishing-on-github-pages-with-github-as-a-backup)); `{command: "…"}` runs any command (`{site}` is the page folder) |
