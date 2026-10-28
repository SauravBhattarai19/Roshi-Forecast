# Roshi Khola flood forecast (experimental)

A live flood forecast for the Roshi Khola in Kavre, Nepal. Every 30 minutes it
reads the latest rain from the rain station and adds weather-model rain
forecasts. It then runs the [MRRpy](https://github.com/SauravBhattarai19/MRRpy)
model 72 hours ahead and updates a web page. The page has river-flow
forecasts for several places and flood maps for several areas.

> [!WARNING]
> **This is a research test, not a flood warning.** Official flood warnings in
> Nepal come from the Department of Hydrology and Meteorology (DHM). The model's
> flows are not yet checked against measured river flow, and in tests they run
> high. There are no warning levels yet.

## What it covers

| | |
|---|---|
| Rain stations | AWS at Roshi (Utrecht University and S4W; alertnepal 496) and AWS at Nala, every 10 minutes through RTS, used with the [alertnepal](https://alertnepal.online) team's permission |
| Rain forecasts | ECMWF, GFS and ICON through [Open-Meteo](https://open-meteo.com), the alertnepal hourly forecast, and a "no more rain" version |
| River flow | Panauti, Khopasi, Mangaltar (BP Highway) and the basin outlet above the Sunkoshi |
| Flood maps (2-D) | Panauti town; Mangaltar (BP Highway) |
| Model | MRRpy at 90 m: Green-Ampt infiltration with impervious land, implicit diffusive-wave routing |

The places come from the September 2024 flood reports and were placed with
OpenStreetMap. They still need checking on the ground.

## How it is split

All the hydrology and hydraulics are the **MRRpy library's**. That covers rain
onto the basin, infiltration, runoff, river routing and the 2-D flood maps.
This repository holds no model code. It only feeds MRRpy and shows what MRRpy
gives:

| Here (`roshi_forecast/`) | In MRRpy |
|---|---|
| reading the rain station and the forecasts (`sources/`) | rain onto the grid, Open-Meteo rain (`MRRpy.core.precip`) |
| building each version's rain files (`rainfiles.py`) | runoff: Green-Ampt, impervious (`MRRpy.core.runoff`) |
| keeping saved states and choosing the start (`states.py`) | saving and loading a model state (`RESTART_FROM`, `SAVE_STATE_AT_HOURS`) |
| running the versions side by side (`models.py`, `cycle.py`) | routing (`MRRpy.core.routing`) |
| the web page and publishing (`products.py`, `website.py`, `web/`) | flood maps (`MRRpy.core.inundation`) |

The forecast code is general. Another river needs only its own `model.yaml`
and `forecast.yaml`.

## Install

The forecast needs an MRRpy with three things:

- **restart files**, so each update carries on from the last one instead of
  starting dry;
- **Open-Meteo rain**;
- **2-D flood maps for several areas.**

No MRRpy release has all three yet. MRRpy's
[`forecast-support`](https://github.com/SauravBhattarai19/MRRpy/tree/forecast-support)
branch does, and this repository installs MRRpy from it:

```bash
pip install -e ".[setup,test]"     # MRRpy from forecast-support; Earth Engine for 'setup'
```

`roshi-forecast` checks the MRRpy it runs on and says what is missing.

## Running it

```bash
roshi-forecast check  -f forecast.yaml    # try every feed; where each point falls (check_map.html)
roshi-forecast setup  -f forecast.yaml    # once: terrain, soil layers, area DEMs, 30-day warm-up
roshi-forecast run    -f forecast.yaml    # one update
roshi-forecast serve  -f forecast.yaml    # an update every 30 minutes, until stopped
roshi-forecast status -f forecast.yaml    # the last update and how fresh the station is
```

Updates run without Earth Engine. Everything they need from it is saved by
`setup` in `static/`.

| File or folder | What it is | In git? |
|---|---|---|
| `forecast.yaml` | the stations, forecasts, places and areas | yes |
| `model.yaml` | the MRRpy settings | yes |
| `rehearsal/` | the September 2024 rehearsal (`forecast.yaml`, `get_imerg.py`) | yes, not its data |
| `docs/` | [how it works](docs/how-it-works.md), [the forecast file](docs/forecast-file.md), [the Roshi set-up](docs/roshi.md) | yes |
| `static/`, `states/`, `archive/`, `cycles/`, `site/` | terrain, saved states, station archive, each update's runs, the web page | no: made on the server |

## Passwords

Passwords never go in this repository. Save a service's sign-in on the server
with:

```bash
scripts/save-credentials.sh        # RTS (rts.wscada.net)
scripts/save-credentials.sh gss    # gss.alertnepal.online
```

It asks for the username and the password, without showing the password. It
saves them in `~/.config/roshi-forecast/credentials.env`, which only you can
read. Run it again to change one service's sign-in; the others are kept.
GitHub Actions, used as the backup, read the same values from the
repository's *Secrets*.

## The September 2024 rehearsal

The forecast was replayed for 25–29 September 2024 on a fake clock. There was
an update every 3 hours. Satellite rain (IMERG) stood in for the station, and
ECMWF forecasts were used as they were issued. The model's own flood, from the
satellite rain (about 383 mm over the basin on 26–28 September), peaked on the
morning of 28 September, Nepal time:

| Place | Highest flow | ECMWF first showed ≥ 80 % of it | ECMWF first showed all of it |
|---|---|---|---|
| Panauti | 686 m³/s | 66 h ahead | 42 h ahead |
| Khopasi | 840 m³/s | 66 h ahead | 54 h ahead |
| Mangaltar (BP Highway) | 2,213 m³/s | 67 h ahead | 31 h ahead |
| Outlet | 2,556 m³/s | 73 h ahead | 31 h ahead |

The forecasts are compared with the model's own result, not with measured
flow. ECMWF swung between runs: at Panauti, successive runs gave 199 to
742 m³/s. In the Bagmati at Khokana, the same soil maps gave about twice too
much runoff, and IMERG gave 1.5–1.7 times too much rain. So these flows are
likely too high.

## Credits

The model is [MRRpy](https://github.com/SauravBhattarai19/MRRpy). Station rain
comes through RTS (Real Time Solutions) and the hourly forecast from
[alertnepal](https://alertnepal.online), with permission. AWS at Roshi belongs
to Utrecht University and S4W. Weather-model
rain comes from [Open-Meteo](https://open-meteo.com) (CC BY 4.0), from ECMWF,
NOAA GFS and DWD ICON. Map data: © OpenStreetMap contributors.
