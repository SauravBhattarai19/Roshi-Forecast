# -*- coding: utf-8 -*-
"""The forecast file: good files load, bad ones list every problem in plain words."""

import pytest
import yaml

from roshi_forecast import SiteFileError, load_site, template
from roshi_forecast.sitefile import NO_RAIN, parse_site


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "model.yaml").write_text(yaml.safe_dump({
        "DEM_PATH": "dem.tif", "RUNOFF_SOURCE": "physical",
        "RUNOFF_MECHANISMS": ["impervious", "infiltration_excess"]}))
    return tmp_path


GOOD = {
    "name": "Roshi", "model": "model.yaml", "display_timezone": "Asia/Kathmandu",
    "rain_stations": [{"name": "AWS at Roshi", "source": "alertnepal", "station": 496},
                      {"name": "Mine", "source": "csv", "path": "g.csv", "lat": 27.5,
                       "lon": 85.5}],
    "rain_forecasts": [{"name": "ECMWF", "source": "open_meteo", "model": "ecmwf_ifs025"},
                       {"name": "GFS", "source": "open_meteo", "model": "gfs_seamless"},
                       {"name": "alertnepal", "source": "alertnepal_forecast"}],
    "main_forecast": "GFS",
    "hydrograph_points": [{"name": "Panauti", "lat": 27.58, "lon": 85.51,
                           "warning_m3s": 100, "danger_m3s": 200}],
    "flood_areas": [{"name": "Panauti town", "box": [85.50, 27.57, 85.53, 27.60],
                     "method": "2d"}],
    "inflows": [{"name": "Up", "source": "csv", "path": "https://example.org/q.csv",
                 "lat": 27.6, "lon": 85.5, "ahead": "recede"}],
}


def _load(folder, data):
    p = folder / "forecast.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return load_site(str(p))


def test_a_good_file(folder):
    s = _load(folder, GOOD)
    assert s.versions() == ["GFS", "ECMWF", "alertnepal", NO_RAIN]       # main first
    assert s.rain_stations[1].options["path"] == str(folder / "g.csv")   # next to the file
    assert s.inflows[0].options["path"].startswith("https://")           # web address kept
    assert s.flood_areas[0].box == (85.50, 27.57, 85.53, 27.60)
    assert s.folder == str(folder) and s.forecast_hours == 48


def test_every_problem_is_listed_with_a_hint(folder):
    bad = dict(GOOD, forcast_hours=24, main_forecast="ECMWF2",
               rain_stations=[{"name": "A", "source": "alertnepl", "station": 1},
                              {"name": "B", "source": "alertnepal"}],
               hydrograph_points=[{"name": "P", "lat": 95, "lon": 85, "warning_m3s": 50,
                                   "danger_m3s": 10, "colour": "red"}],
               flood_areas=[{"name": "X", "box": [85.6, 27.5, 85.5, 27.6]}])
    with pytest.raises(SiteFileError) as e:
        _load(folder, bad)
    msg = str(e.value)
    for words in ("did you mean 'forecast_hours'", "did you mean 'alertnepal'",
                  "needs 'station'", "did you mean 'ECMWF'", "lat = 95 is out of range",
                  "danger_m3s is below warning_m3s", "'colour' is not a point setting",
                  "west < east"):
        assert words in msg, words
    assert "8 problem(s)" in msg or "problem(s)" in msg


def test_models_that_cannot_run_for_months_are_refused(folder):
    (folder / "model.yaml").write_text(yaml.safe_dump({"RUNOFF_SOURCE": "scs_cn"}))
    with pytest.raises(SiteFileError, match="scs_cn"):
        _load(folder, GOOD)
    (folder / "model.yaml").write_text(yaml.safe_dump({
        "RUNOFF_SOURCE": "physical", "RUNOFF_MECHANISMS": ["saturation_excess"]}))
    with pytest.raises(SiteFileError, match="VSA_PER_POLYGON: false"):
        _load(folder, GOOD)
    (folder / "model.yaml").write_text(yaml.safe_dump({"OUTPUT_INTERVAL_SECONDS": 700}))
    with pytest.raises(SiteFileError, match="divide an hour"):
        _load(folder, GOOD)


def test_the_template_parses_once_its_files_exist(tmp_path):
    (tmp_path / "model.yaml").write_text("{}\n")
    data = yaml.safe_load(template())
    s = parse_site(data, str(tmp_path / "forecast.yaml"))
    assert s.main_forecast == "ECMWF" and len(s.versions()) == 4


def test_missing_model_file(tmp_path):
    with pytest.raises(SiteFileError, match="model: file not found"):
        parse_site(dict(GOOD), str(tmp_path / "forecast.yaml"))


def test_cli_new_and_github_workflow(tmp_path, capsys):
    from roshi_forecast.cli import main
    d = tmp_path / "site"
    assert main(["new", str(d)]) == 0
    assert (d / "forecast.yaml").is_file() and (d / "model.yaml").is_file()
    assert main(["new", str(d)]) == 1                      # never overwrites
    data = yaml.safe_load((d / "forecast.yaml").read_text())
    data["website"]["publish"] = {"git": {"remote": "git@github.com:me/flood.git"}}
    (d / "forecast.yaml").write_text(yaml.safe_dump(data))
    (d / "gauge.csv").write_text("time_utc,rain_mm\n")
    assert main(["github-workflow", "-f", str(d / "forecast.yaml")]) == 0
    wf = yaml.safe_load((d / ".github" / "workflows" / "forecast-backup.yml").read_text())
    step = wf["jobs"]["cycle"]["steps"][-1]["run"]
    assert "--only-if-stale 45" in step and "--restore-state" in step
    assert wf[True]["schedule"][0]["cron"] == "7,37 * * * *"           # YAML reads 'on' as True
