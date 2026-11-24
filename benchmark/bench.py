"""Before/after benchmark.

    python benchmark/bench.py               # offline: the call-by-call cost model, no key, no cost
    python benchmark/bench.py --live        # real: the same bug fixed twice on the Claude API (all fixes off, then on)
    python benchmark/bench.py --live --each # real: also each fix on its own (8 runs; a few dollars)

The live task is a real bug (fixture/billing: 1,960 passing tests and one failing one, the same repo as the reel).
Each run gets a fresh copy of the fixture, so runs don't see each other's edits.
"""
from __future__ import annotations

import argparse
import dataclasses
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.path.insert(0, str(HERE.parent / "python" / "examples"))
from agent_cost.simulate import FIXES, Run, report  # noqa: E402


def offline() -> None:
    print("Modelled 20-call coding run (edit agent_cost/simulate.py Run() to match your agent)\n")
    print(f"{'':16s} {'cost/run':>9s} {'calls':>6s} {'saving':>7s}")
    for row in report(Run()):
        print(f"{row['name']:16s} ${row['cost']:8.3f} {row['calls']:6d} {('-' + format(row['saving'] * 100, '.0f') + '%') if row['saving'] else '':>7s}")
    print("\nEach fix alone, then all seven together. Savings don't simply add up: they overlap, and pruning edits history,"
          "\nwhich breaks the cache unless it runs in batches.")


def live(each: bool) -> None:
    from agent_loop import Config, run_agent
    task = "The test suite has a failing test. Find the bug and make all tests pass."
    off = Config(**{f.name: False for f in dataclasses.fields(Config) if f.type in (bool, "bool")})
    configs = [("all fixes off", off), ("all fixes on", Config())]
    if each:
        name_map = dict(cache="cache", trim="trim", prune="prune", parallel="parallel", stop="stop", tools="tools", effort="effort")
        configs[1:1] = [(f"{k} alone", dataclasses.replace(off, **{v: True})) for k, v in name_map.items()]
    rows = []
    for name, cfg in configs:
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp) / "billing"
            shutil.copytree(HERE / "fixture" / "billing", repo)
            print(f"\n== {name}")
            r = run_agent(str(repo), task, cfg)
            rows.append((name, r))
    base = rows[0][1]["usd"]
    print(f"\n{'':16s} {'cost':>8s} {'calls':>6s} {'saving':>7s}  tests  stopped because")
    for name, r in rows:
        s = 1 - r["usd"] / base if base else 0
        print(f"{name:16s} ${r['usd']:7.4f} {r['n_calls']:6d} {('-' + format(s * 100, '.0f') + '%') if name != rows[0][0] else '':>7s}  {'pass' if r['tests_pass'] else 'FAIL':5s}  {r['reason']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--each", action="store_true")
    a = ap.parse_args()
    live(a.each) if a.live else offline()
