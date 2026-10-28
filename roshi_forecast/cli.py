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
      - run: roshi-forecast run {target} --restore-state --only-if-stale {stale}
"""


def _site(args):
    from . import load_site
    return load_site(args.forecast or "forecast.yaml")


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
    from .prepare import SetupError, latest_flood_run, map_dems, setup_site
    try:
        if args.maps_only:
            site = _site(args)
            map_dems(site, latest_flood_run(site))
            return 0
        setup_site(_site(args), force_terrain=args.terrain, warm=not args.no_warm_up,
                   parallel=not args.serial)
    except SetupError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


def _targets(args):
    """(places file or None, [(place id, site)]): -p, else -f, else places.yaml or
    forecast.yaml in this folder."""
    from . import load_site
    from .places import load_portal, sites
    places = getattr(args, "places", None)
    if not places and not args.forecast and os.path.isfile("places.yaml"):
        places = "places.yaml"
    if places:
        portal = load_portal(places)
        return portal, [(p.id, site) for p, site in sites(portal)]
    site = load_site(args.forecast or "forecast.yaml")
    return None, [(None, site)]


def _run_once(site, args, git=None, subdir="", publish=True):
    from .cycle import run_cycle
    if getattr(args, "restore_state", False):
        from .publish import restore_state
        restore_state(site, git=git, subdir=subdir)
    return run_cycle(site, publish=publish and not args.no_publish, parallel=not args.serial,
                     only_if_stale=args.only_if_stale)


def _round(args, portal, items):
    """One update of every place, then (several places) the site → exit code."""
    if portal is None:
        st = _run_once(items[0][1], args)
        return 0 if st.get("ok") or st.get("skipped") else 1
    from . import places
    bad, ran = [], False
    for pid, site in items:
        print(f"── {pid} ──")
        try:
            st = _run_once(site, args, git=(portal.publish or {}).get("git"), subdir=pid,
                           publish=False)
            ran = ran or not st.get("skipped")
            if not (st.get("ok") or st.get("skipped")):
                bad.append(pid)
        except Exception as exc:                          # noqa: BLE001 — the others go on
            print(f"[ERROR] {pid}: {exc}", file=sys.stderr)
            bad.append(pid)
    if ran or not args.only_if_stale:
        places.build(portal)
        if not args.no_publish:
            places.publish(portal)
    if bad:
        print(f"Updates failed for: {', '.join(bad)}", file=sys.stderr)
    return 1 if bad else 0


def _cmd_run(args):
    try:
        return _round(args, *_targets(args))
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


def _cmd_serve(args):
    portal, items = _targets(args)
    minutes = portal.every_minutes if portal else items[0][1].every_minutes
    every = 60.0 * minutes
    what = (f"{len(items)} places" if len(items) > 1 else "the place") if portal else "a cycle"
    print(f"Updating {what} every {minutes} minutes; stop with Ctrl+C.")
    while True:
        t0 = time.time()
        try:
            _round(args, portal, items)
        except Exception as exc:                          # noqa: BLE001 — keep serving
            print(f"[ERROR] cycle failed: {exc}", file=sys.stderr)
        wait = every - ((time.time() - 120.0) % every)      # 2 min after each half hour
        print(f"Next cycle in {wait / 60:.0f} min (this one took {time.time() - t0:.0f} s).")
        time.sleep(wait)


def _cmd_site(args):
    from . import places
    portal, _ = _targets(args)
    if portal is None:
        print("[ERROR] 'site' needs a places file (-p places.yaml)", file=sys.stderr)
        return 1
    places.build(portal)
    if args.publish:
        places.publish(portal)
    return 0


def _cmd_replay(args):
    from .replay import parse_time, replay
    df = replay(_site(args), parse_time(args.start), parse_time(args.end),
                every_hours=args.every, warm_up_days=args.warm_up_days,
                parallel=not args.serial)
    if len(df):
        print(df.groupby(["point", "version"])["peak_m3s"].max().round(1).to_string())
    return 0


def _status_one(site, json_too):
    import json
    from . import archive
    from .cycle import last_status
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
    if json_too:
        print(json.dumps(st, indent=1))
    return 0 if st.get("ok") else 1


def _cmd_status(args):
    portal, items = _targets(args)
    code = 0
    for pid, site in items:
        if portal:
            print(f"── {pid} ──")
        code = max(code, _status_one(site, args.json))
    return code


def _cmd_workflow(args):
    portal, items = _targets(args)
    if portal:
        folder, minutes = portal.folder, portal.every_minutes
        target = "-p " + os.path.relpath(portal.path, folder)
    else:
        site = items[0][1]
        folder, minutes = site.folder, site.every_minutes
        target = "-f " + os.path.relpath(site.path, folder)
    out = args.output or os.path.join(folder, ".github", "workflows", "forecast-backup.yml")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    minute = (minutes // 4) or 7
    cron = f"{minute},{minute + 30} * * * *" if minutes == 30 else f"{minute} * * * *"
    with open(out, "w") as f:
        f.write(WORKFLOW.format(cron=cron, stale=args.stale, target=target))
    print(f"Written: {out}")
    print("Commit it, with each place's forecast.yaml, model.yaml and static/, to the "
          "repository named in publish: git: remote:.")
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

    def with_file(name, help, func, places=False):
        q = fs.add_parser(name, help=help)
        q.add_argument("-f", "--forecast", default=None,
                       help="one place's forecast file (default: forecast.yaml)")
        if places:
            q.add_argument("-p", "--places", default=None,
                           help="a places file: every place in it, and the site of them all "
                                "(default: places.yaml when there is one here)")
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
    q.add_argument("--maps-only", action="store_true",
                   help="only prepare the flood maps' DEMs (after adding an area or "
                        "basin_map), from the newest run")
    q.add_argument("--serial", action="store_true", help="run models in this process")
    for name, help, func in (("run", "update the forecast now (one place, or every place)", _cmd_run),
                             ("serve", "update every every_minutes, until stopped",
                              _cmd_serve)):
        q = with_file(name, help, func, places=True)
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
    q = with_file("status", "the last cycle and how fresh each station is", _cmd_status,
                  places=True)
    q.add_argument("--json", action="store_true", help="also print status.json")
    q = with_file("github-workflow", "write the GitHub Actions backup workflow", _cmd_workflow,
                  places=True)
    q.add_argument("-o", "--output", default=None, help="where to write it")
    q.add_argument("--stale", type=float, default=45.0,
                   help="minutes without a cycle before the backup runs (default 45)")
    q = with_file("site", "write the web site of every place (front page + each place's page)",
                  _cmd_site, places=True)
    q.add_argument("--publish", action="store_true", help="also publish it (publish: in "
                                                          "the places file)")
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
