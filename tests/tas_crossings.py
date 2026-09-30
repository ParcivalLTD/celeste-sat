#!/usr/bin/env python3
"""
tas_crossings.py -- can the community TAS cross a room boundary sooner?

For each room change of the chained TAS (tests/chain_tas.py), runs
tools/cross.py: the TAS's first U - A frames in the room before are kept,
the rest of that room, the transition and the first B frames of the next
room are free, and CBMC is asked whether she can be in exactly the TAS's
state after B frames in the next room one frame sooner. A "no" for every
frame she could leave on proves the TAS cannot gain a frame there without
changing what came before or what comes after.

    python3 tests/tas_crossings.py [--before 6] [--after 3] [--timeout 1800] [--from lvl_4]

Run tests/chain_tas.py first. Each boundary's result is in
build/cross_<a>_<b>/result.json; a summary is printed.
"""
import argparse, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from solve import read_tas  # noqa: E402
from tas_endings import ORDER  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--before", type=int, default=6, help="free frames at the end of the room before (default 6)")
    ap.add_argument("--after", type=int, default=3, help="target: the TAS's state after this many frames in the next room")
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--from", dest="start", default=ORDER[0])
    a = ap.parse_args()
    for ra, rb in zip(ORDER[ORDER.index(a.start):], ORDER[ORDER.index(a.start) + 1:]):
        route_a = os.path.join(ROOT, "build", "chain_tas", ra, "route.tas")
        route_b = os.path.join(ROOT, "build", "chain_tas", rb, "route.tas")
        if not (os.path.exists(route_a) and os.path.exists(route_b)):
            print(f"{ra} -> {rb}: not played by tests/chain_tas.py, skipped")
            continue
        entry = os.path.join(ROOT, "build", "chain_tas", f"entry_{ra}.h")
        out = os.path.join(ROOT, "build", f"cross_{ra}_{rb}")
        cmd = [sys.executable, f"{ROOT}/tools/cross.py", f"{ROOT}/rooms/vanilla/1a_{ra}.txt", route_a,
               f"{ROOT}/rooms/vanilla/1a_{rb}.txt", route_b, "--keep", str(len(read_tas(route_a)) - a.before),
               "--target", str(a.after), "--timeout", str(a.timeout), "--jobs", str(a.jobs), "--out", out]
        if os.path.exists(entry):
            cmd += ["--start", entry]
        r = subprocess.run(cmd, capture_output=True, text=True)
        last = (r.stdout.strip().splitlines() or [r.stderr.strip()[-300:]])[-1]
        print(f"{ra} -> {rb}: {last}", flush=True)


if __name__ == "__main__":
    main()
