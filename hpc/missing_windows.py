#!/usr/bin/env python3
"""
missing_windows.py -- the windows of a width that have no result at all.

    python3 hpc/missing_windows.py --width 16
    python3 hpc/missing_windows.py --width 16 --json hpc/leonardo_missing_w16.json
    python3 hpc/missing_windows.py --width 16 --merge build/edge_w16.json --json hpc/edge_flagged_w16.json
    python3 hpc/missing_windows.py --width 18 --rooms lvl_1

A room has (frames of its route - W - 1) windows, K = 0 .. frames - W - 2, the
same count hpc/make_tasks.py splits into tasks (at W = 12 that is exactly
2,028 over Chapter 1). A window is missing if hpc/summary.py's collect() finds
neither a verdict nor a timeout for it, e.g. because its Slurm task hit the
time limit before the query finished. Routes come from
results/leonardo/chain_tas/<room>/route.tas, results from results/leonardo/
(or --dir).

--merge adds the missing windows to a {room: [K, ...]} file such as the one
experiments/edge_windows.py --json writes, so that the edge re-check
(hpc/edge_chunks.py, hpc/run_flagged.sh) runs them too. --json writes the
result in the same shape; without it the rooms and K are printed.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "hpc")]
from celeste_sat.community import CH1_ORDER  # noqa: E402
from celeste_sat.tas import read_tas  # noqa: E402
from summary import collect  # noqa: E402


def ranges(ks):
    """[1, 2, 3, 7] -> "1-3, 7" """
    out, run = [], []
    for k in ks + [None]:
        if run and (k is None or k != run[-1] + 1):
            out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else f"{run[0]}")
            run = []
        if k is not None:
            run.append(k)
    return ", ".join(out)


def missing(width, rooms, results_dir):
    """-> {room: [K, ...]} of the windows with no result, rooms in chapter order"""
    res, _ = collect([results_dir])
    out = {}
    for room in rooms:
        route = os.path.join(results_dir, "chain_tas", room, "route.tas")
        if not os.path.exists(route):
            sys.exit(f"{route} missing")
        have = res.get((room, width), {})
        ks = [k for k in range(len(read_tas(route)) - width - 1) if k not in have]
        if ks:
            out[room] = ks
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--rooms", help="comma-separated rooms (default: all 19)")
    ap.add_argument("--dir", default=os.path.join(ROOT, "results", "leonardo"), help="results to read (default results/leonardo)")
    ap.add_argument("--merge", help="a {room: [K, ...]} file to add the missing windows to")
    ap.add_argument("--json", help="write {room: [K, ...]} here")
    a = ap.parse_args()
    rooms = a.rooms.split(",") if a.rooms else CH1_ORDER
    miss = missing(a.width, rooms, a.dir)
    total = sum(map(len, miss.values()))
    out = miss
    if a.merge:
        base = json.load(open(a.merge))
        added = sum(len(set(ks) - set(base.get(r, []))) for r, ks in miss.items())
        out = {r: sorted(set(base.get(r, [])) | set(miss.get(r, [])))
               for r in CH1_ORDER if r in base or r in miss}
        out.update({r: ks for r, ks in base.items() if r not in out})
        print(f"{a.merge}: {sum(map(len, base.values()))} windows, {added} missing ones added, "
              f"{sum(map(len, out.values()))} in all")
    for room, ks in miss.items():
        print(f"{room:8s} {len(ks):3d} missing: {ranges(ks)}")
    print(f"W={a.width}: {total} windows with no result in {os.path.relpath(a.dir, ROOT)}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1)
            f.write("\n")


if __name__ == "__main__":
    main()
