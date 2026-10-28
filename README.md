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

On the computer that will run it (Linux or macOS):

```bash
git clone https://github.com/SauravBhattarai19/Roshi-Forecast.git
cd Roshi-Forecast
scripts/install.sh                          # .venv with this package and its MRRpy
.venv/bin/roshi-forecast service install    # runs by itself from now on
.venv/bin/roshi-forecast doctor             # what is ready, what to fix
```

**Handing it over? Read the [operator guide](docs/operator-guide.md).** It
covers the sign-ins, what to edit for each change, and what to do when
something is wrong.

The forecast needs an MRRpy with three things:

- **restart files**, so each update carries on from the last one instead of
  starting dry;
- **Open-Meteo rain**;
- **2-D flood maps for several areas.**

MRRpy's
[`forecast-support`](https://github.com/SauravBhattarai19/MRRpy/tree/forecast-support)
branch has all three. The install takes MRRpy from it (developers:
`pip install -e ".[setup,test]"`). `roshi-forecast` checks the MRRpy it runs on
and says what is missing.

## Running it

Each place is a folder under `places/`, with its own `forecast.yaml` and
`model.yaml`. `places.yaml` lists the places and makes one web site of them
all. The front page has every place on a map, a card for each and their
warnings. Each place has its own page under `public/<place>/`, with these
parts:

- a map of every river, coloured by flow; click any river for its forecast;
- 2-D flood maps;
- the hydrographs of each forecast;
- day-by-day tiles;
- the rain stations.

```bash
roshi-forecast serve      # keeps going: every 30 min each place is updated and the site published
roshi-forecast doctor     # is everything ready and running? what to fix, in words
roshi-forecast status     # each place's last update and its stations
roshi-forecast run        # one update of every place now
roshi-forecast site       # only rebuild the site (public/)
roshi-forecast check -f places/roshi/forecast.yaml   # try every feed; where each point falls
```

`serve` reads the settings again every round. Edit a file, and the next round
uses it:

- a new place in `places.yaml` is set up by itself;
- a place whose `model.yaml` changed is set up again;
- a new flood area gets its DEM.

A file with a mistake keeps its last good version, and `doctor` reports it.
`roshi-forecast service install` keeps `serve` running. It uses a systemd user
service, or cron where there is no systemd. Updates run without Earth Engine:
everything they need from it is saved by setup in `static/`.

### Adding a place

```bash
roshi-forecast new places/nakhu --name "Nakhu Khola" --outlet 27.62,85.29
```

This writes `places/nakhu/model.yaml` (the Roshi physics, the UTM zone of the
outlet) and `forecast.yaml` (ECMWF, GFS and ICON; the outlet as a point; a 2-D
map of the whole basin). It also adds the place to `places.yaml`. Then put the
towns and bridges to watch under `hydrograph_points`. `serve` sets the place up
by itself: setup widens the DEM box until the basin fits. Or run the setup now:
`roshi-forecast setup -f places/nakhu/forecast.yaml`. The folder's name is the
place's web address (`…/nakhu/`).

| File or folder | What it is | In git? |
|---|---|---|
| `places.yaml` | the places, the site's title, where it is published | yes |
| `places/<place>/forecast.yaml` | the stations, forecasts, points and areas | yes |
| `places/<place>/model.yaml` | the MRRpy settings | yes |
| `places/roshi/rehearsal/` | the September 2024 rehearsal (`forecast.yaml`, `get_imerg.py`) | yes, not its data |
| `docs/` | [operator guide](docs/operator-guide.md), [how it works](docs/how-it-works.md), [the forecast file](docs/forecast-file.md), [the Roshi set-up](docs/roshi.md) | yes |
| `places/<place>/static/`, `states/`, `archive/`, `cycles/`, `site/` | terrain, saved states, station archive, each update's runs, the place's page | no: made on the server |
| `public/` | the whole web site | no: made on the server, published to `gh-pages` |

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
