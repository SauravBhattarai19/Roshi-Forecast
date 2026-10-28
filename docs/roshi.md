# Example: Roshi Khola

The Roshi Khola drains the hills south-east of Kathmandu. It passes Panauti
and Khopasi and follows the BP Highway down to the Sunkoshi. In late September
2024 it flooded Panauti and Roshi Rural Municipality and cut the highway. This
example is the forecast MRRpy was first tested on. Its places come from the
2024 flood reports and were placed with OpenStreetMap. Check them with
`roshi-forecast check` and correct them before relying on the forecast.

## The model: `model.yaml`

The settings are the same as for the Bagmati at Khokana: Green-Ampt infiltration
with impervious land, and implicit diffusive routing on a 90 m grid.

```yaml
DEM_PATH: ''
DEM_BOUNDS_WGS84: [85.38, 27.36, 85.90, 27.70]
DEM_SOURCE: fabdem
DEM_SCALE_M: 90
OUTPUT_POINT: [27.44238, 85.80873]       # on the Roshi, 1.5 km above the Sunkoshi
TARGET_CRS_EPSG: EPSG:32645
DELINEATION_ENGINE: pyflwdir
GEE_PROJECT: your-earth-engine-project   # used by setup only
PRECIP_METHOD: idw                       # the forecast writes the rain files
RUNOFF_SOURCE: physical
RUNOFF_MECHANISMS: [impervious, infiltration_excess]
IMPERVIOUS_SOURCE: lcz
GA_KSAT_SOURCE: gee
GA_SUCTION_SOURCE: texture
VSA_SD_SOURCE: gee
MANNINGS_N_SOURCE: lcz
MANNINGS_N_CHANNEL: 0.035
CHANNEL_QBF_M3S: wecs_nepal
CHANNEL_GEOMETRY: discharge
CHANNEL_SUBGRID: true
ROUTING_SCHEME: diffusive_implicit
IMPLICIT_CFL_TARGET: 2.0
OUTPUT_INTERVAL_SECONDS: 600
```

The outlet is placed above the confluence on purpose. A point placed on the
confluence itself can move onto the much larger Sunkoshi.

## The forecast: `forecast.yaml`

```yaml
name: Roshi Khola flood forecast
model: model.yaml
display_timezone: Asia/Kathmandu
forecast_hours: 72
warm_up_days: 30
station_silent_minutes: 120          # AWS 496 uploads about once an hour
rain_stations:
  - {name: AWS at Roshi, source: alertnepal, station: 496}
rain_forecasts:
  - {name: ECMWF, source: open_meteo, model: ecmwf_ifs025}
  - {name: GFS, source: open_meteo, model: gfs_seamless}
  - {name: ICON, source: open_meteo, model: icon_seamless}
  - {name: alertnepal, source: alertnepal_forecast}
main_forecast: ECMWF
hydrograph_points:
  - {name: Panauti, lat: 27.58491, lon: 85.52141}
  - {name: Khopasi, lat: 27.56193, lon: 85.53829}
  - {name: Mangaltar (BP Highway), lat: 27.47640, lon: 85.74547}
flood_areas:
  - {name: Panauti town, box: [85.505, 27.574, 85.532, 27.592], method: 2d}
  - {name: Mangaltar (BP Highway), box: [85.725, 27.465, 85.762, 27.487], method: 2d}
website:
  title: Roshi Khola flood forecast (experimental)
```

The forecast looks 72 hours ahead, since storms here often show in the
weather models two or three days out. The station uploads its 10-minute
readings about once an hour, so it counts as missing only after two hours of
silence.

There is one rain station, AWS 496 "AWS at Roshi" (Utrecht University and S4W),
so the measured rain is the same over the whole basin. The forecasts add the
pattern. There are no warning levels yet. GA runoff with these soil maps ran
high at Khokana, so the levels should come from the model's own flows, not from
gauge records. The [September 2024 rehearsal](../README.md#the-september-2024-rehearsal)
gives the model's flows for that flood.

## Running it

```bash
roshi-forecast check -f forecast.yaml
roshi-forecast setup -f forecast.yaml
roshi-forecast run -f forecast.yaml
```

Every update fetches ECMWF, GFS and ICON once an hour, at 10 km spacing. Each
is a few dozen Open-Meteo calls, about 1,800 a day in all. That is well inside
the free 10,000.
