# -*- coding: utf-8 -*-
"""``roshi-forecast …`` — the command line of the live flood forecast."""

import argparse
import os
import sys
import time

WORKFLOW = """\
# Backup runner for the flood forecast (written by 'roshi-forecast github-workflow').
# It runs a cycle only when the main server has not published for {stale} minutes,
# carrying on from the server's last state (the 'state' branch). GitHub runs
# schedules on a best-effort basis and switches them off after 60 days without
# a commit to the repository.
name: flood-forecast-backup
on:
  schedule:
    - cron: "{cron}"
  workflow_dispatch: {{}}
permissions:
  contents: write
concurrency: {{group: flood-forecast, cancel-in-progress: false}}
jobs:
  cycle:
    runs-on: ubuntu-latest
    timeout-minutes: 40
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {{python-version: "3.11"}}
      - run: pip install .            # this repository, with the MRRpy it names
      - name: Configure git for publishing
        run: |
          git config --global user.name "roshi-forecast (backup)"
          git config --global user.email "forecast@localhost"
          git config --global url."https://x-access-token:${{{{ secrets.GITHUB_TOKEN }}}}@github.com/".insteadOf "git@github.com:"
      - run: roshi-forecast run -f {forecast} --restore-state --only-if-stale {stale}
"""


def _site(args):
    from . import load_site
    return load_site(args.forecast)


def _cmd_new(args):
    from . import template
    from MRRpy.interactive.render import save_yaml
    from MRRpy.config import Config
    os.makedirs(args.folder, exist_ok=True)
    fc = os.path.join(args.folder, "forecast.yaml")
    if os.path.exists(fc) and not args.force:
        print(f"[ERROR] {fc} already exists (use --force to replace it)", file=sys.stderr)
        return 1
    with open(fc, "w") as f:
        f.write(template())
    model = os.path.join(args.folder, "model.yaml")
    if not os.path.exists(model):
        save_yaml(Config(), model, full=False, source="roshi-forecast new")
    print(f"Written: {fc}")
    print(f"         {model}")
    print("Next:")
    print(f"  1. Set the basin in {model} (or: MRRpy wizard --edit {model})")
    print(f"  2. List your stations, forecasts, points and areas in {fc}")
    print(f"  3. roshi-forecast check -f {fc}")
    print(f"  4. roshi-forecast setup -f {fc}")
    print(f"  5. roshi-forecast run -f {fc}")
    return 0


def _cmd_check(args):
    from .check import check_site
    out = check_site(_site(args))
    bad = [x["name"] for k in ("stations", "forecasts", "points", "inflows")
           for x in out.get(k, []) if not x.get("ok")]
    if bad:
        print(f"Problems with: {', '.join(bad)}")
    return 1 if bad else 0


def _cmd_setup(args):
    from .prepare import SetupError, setup_site
    try:
        setup_site(_site(args), force_terrain=args.terrain, warm=not args.no_warm_up,
                   parallel=not args.serial)
    except SetupError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


def _run_once(site, args):
    from .cycle import run_cycle
    if getattr(args, "restore_state", False):
        from .publish import restore_state
        restore_state(site)
    st = run_cycle(site, publish=not args.no_publish, parallel=not args.serial,
                   only_if_stale=args.only_if_stale)
    return 0 if st.get("ok") or st.get("skipped") else 1


def _cmd_run(args):
    try:
        return _run_once(_site(args), args)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


def _cmd_serve(args):
    site = _site(args)
    every = 60.0 * site.every_minutes
    print(f"A cycle every {site.every_minutes} minutes; stop with Ctrl+C.")
    while True:
        t0 = time.time()
        try:
            _run_once(site, args)
        except Exception as exc:                          # noqa: BLE001 — keep serving
            print(f"[ERROR] cycle failed: {exc}", file=sys.stderr)
        wait = every - ((time.time() - 120.0) % every)      # 2 min after each half hour
        print(f"Next cycle in {wait / 60:.0f} min (this one took {time.time() - t0:.0f} s).")
        time.sleep(wait)


def _cmd_replay(args):
    from .replay import parse_time, replay
    df = replay(_site(args), parse_time(args.start), parse_time(args.end),
                every_hours=args.every, warm_up_days=args.warm_up_days,
                parallel=not args.serial)
    if len(df):
        print(df.groupby(["point", "version"])["peak_m3s"].max().round(1).to_string())
    return 0


def _cmd_status(args):
    import json
    from . import archive
    from .cycle import last_status
    site = _site(args)
    st = last_status(site)
    if not st:
        print("No cycle has run yet.")
        return 1
    print(f"Last cycle {st['cycle_utc']} UTC: {'ok' if st.get('ok') else 'FAILED'} "
          f"in {st.get('seconds', '?')} s; station rain to {st.get('t_obs_utc')} UTC")
    for s in st.get("steps", []):
        print(f"  {'ok  ' if s['ok'] else 'FAIL'} {s['step']}  {s.get('note', '')}")
    for v, r in st.get("versions", {}).items():
        print(f"  version {v}: {'ran' if r.get('ok') else 'FAILED ' + str(r.get('error'))}")
    for key, (meta, table) in archive.stations(site).items():
        print(f"  station {meta['name']}: last report {meta.get('last_report_utc')} UTC, "
              f"{meta.get('rows')} rows kept")
    if args.json:
        print(json.dumps(st, indent=1))
    return 0 if st.get("ok") else 1


def _cmd_workflow(args):
    site = _site(args)
    out = args.output or os.path.join(site.folder, ".github", "workflows", "forecast-backup.yml")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    minute = (site.every_minutes // 4) or 7
    cron = f"{minute},{minute + 30} * * * *" if site.every_minutes == 30 else f"{minute} * * * *"
    with open(out, "w") as f:
        f.write(WORKFLOW.format(cron=cron, stale=args.stale,
                                forecast=os.path.relpath(site.path, site.folder)))
    print(f"Written: {out}")
    print("Commit the forecast folder (forecast.yaml, model.yaml, static/) to the repository "
          "named in website: publish: git: remote:, with this file.")
    return 0


def build_parser():
    from MRRpy import __version__ as mrrpy_version
    from . import __version__
    p = argparse.ArgumentParser(prog="roshi-forecast",
                                description="A live flood forecast built on the MRRpy model: "
                                            "see 'roshi-forecast new' to start.")
    p.add_argument("--version", action="version",
                   version=f"roshi-forecast {__version__} (MRRpy {mrrpy_version})")
    fs = p.add_subparsers(dest="command", required=True)

    def with_file(name, help, func):
        q = fs.add_parser(name, help=help)
        q.add_argument("-f", "--forecast", default="forecast.yaml",
                       help="the forecast file (default: forecast.yaml)")
        q.set_defaults(func=func)
        return q

    q = fs.add_parser("new", help="write a forecast file and a model file to start from")
    q.add_argument("folder", help="folder for the new forecast")
    q.add_argument("--force", action="store_true", help="replace an existing forecast.yaml")
    q.set_defaults(func=_cmd_new)
    with_file("check", "try every feed and show where each point falls on the rivers",
              _cmd_check)
    q = with_file("setup", "prepare the site once: terrain, layers, warm-up, area DEMs",
                  _cmd_setup)
    q.add_argument("--terrain", action="store_true", help="prepare the terrain again")
    q.add_argument("--no-warm-up", action="store_true", help="skip the warm-up run")
    q.add_argument("--serial", action="store_true", help="run models in this process")
    for name, help, func in (("run", "run one forecast cycle now", _cmd_run),
                             ("serve", "run a cycle every every_minutes, until stopped",
                              _cmd_serve)):
        q = with_file(name, help, func)
        q.add_argument("--no-publish", action="store_true", help="do not publish the page")
        q.add_argument("--serial", action="store_true", help="run the versions one by one "
                                                             "in this process")
        q.add_argument("--only-if-stale", type=float, default=None, metavar="MIN",
                       help="do nothing if a cycle finished less than MIN minutes ago")
        q.add_argument("--restore-state", action="store_true",
                       help="first fetch the newest states from the git 'state' branch")
    q = with_file("replay", "rehearse a past flood on a fake clock", _cmd_replay)
    q.add_argument("--start", required=True, help="first cycle, UTC (YYYY-MM-DD HH:MM)")
    q.add_argument("--end", required=True, help="last cycle, UTC")
    q.add_argument("--every", type=float, default=3.0, help="hours between cycles (default 3)")
    q.add_argument("--warm-up-days", type=float, default=None,
                   help="days of rain before the first cycle (default: warm_up_days)")
    q.add_argument("--serial", action="store_true", help="run models in this process")
    q = with_file("status", "the last cycle and how fresh each station is", _cmd_status)
    q.add_argument("--json", action="store_true", help="also print status.json")
    q = with_file("github-workflow", "write the GitHub Actions backup workflow", _cmd_workflow)
    q.add_argument("-o", "--output", default=None, help="where to write it")
    q.add_argument("--stale", type=float, default=45.0,
                   help="minutes without a cycle before the backup runs (default 45)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command != "new":
        from . import missing_mrrpy_features
        missing = missing_mrrpy_features()
        if missing:
            print("[ERROR] The installed MRRpy lacks what the forecast needs: "
                  + "; ".join(missing) + ". Install the MRRpy named in README.md.",
                  file=sys.stderr)
            return 1
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
