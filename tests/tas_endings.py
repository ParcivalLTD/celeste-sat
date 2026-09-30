#!/usr/bin/env python3
"""
tas_endings.py -- can the community TAS leave a room sooner at its end?

For each room tests/chain_tas.py played (build/chain_tas/<room>/: the room,
the state she enters it with and the TAS's inputs), keep the TAS's first
U - K frames (U: the frame it leaves the room on), and ask CBMC whether any
inputs leave the room within K - 1 more frames, i.e. one frame sooner
(harness/solve.c). "no" proves that ending cannot be shortened with those
first frames fixed; a route found is a faster exit from this room -- which
still has to work for the next room (tools/cross.py checks that).

    python3 tests/tas_endings.py [--k 10] [--timeout 1800] [--rooms lvl_4,lvl_5]

Run tests/chain_tas.py first. Results go to build/tas_endings.json.
"""
import argparse, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from solve import cbmc, read_tas, write_tas  # noqa: E402

ORDER = ["lvl_1", "lvl_2", "lvl_3", "lvl_4", "lvl_3b", "lvl_5", "lvl_6", "lvl_6a", "lvl_6b", "lvl_6c", "lvl_7",
         "lvl_8", "lvl_8b", "lvl_9", "lvl_9b", "lvl_10a", "lvl_11", "lvl_12", "lvl_12a"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=10, help="frames at the end of the TAS's room left free (default 10)")
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--rooms", help="comma-separated rooms (default: all that tests/chain_tas.py played)")
    a = ap.parse_args()
    rooms = a.rooms.split(",") if a.rooms else ORDER
    out_path = os.path.join(ROOT, "build", "tas_endings.json")
    results = json.load(open(out_path)) if os.path.exists(out_path) else {}
    for room in rooms:
        bdir = os.path.join(ROOT, "build", "chain_tas", room)
        route = os.path.join(bdir, "route.tas")
        if not os.path.exists(route):
            print(f"{room}: not played by tests/chain_tas.py, skipped")
            continue
        r = subprocess.run([f"{bdir}/sim", route], capture_output=True, text=True).stdout
        m = re.search(r"EXIT at frame (\d+)", r)
        if not m:
            print(f"{room}: the TAS's inputs do not leave it in the model, skipped")
            continue
        u = int(m.group(1))
        keep = u - a.k
        start = f"ending_start_{keep}.h"
        subprocess.run([f"{bdir}/sim", "-s", str(keep), os.path.join(bdir, start), route], capture_output=True)
        try:
            found, frames, dt = cbmc(bdir, a.k - 1, start, a.timeout)
        except SystemExit:                          # CBMC killed (out of memory) or crashed
            found, frames, dt = None, None, 0.0
        verdict = "TIMEOUT" if found is None else "no"
        if found:                                   # replay the TAS's first frames + the solver's
            faster = os.path.join(bdir, "ending_faster.tas")
            write_tas(faster, read_tas(route)[:keep] + frames, [f"{room}: TAS frames 1-{keep}, then CBMC"])
            r = subprocess.run([f"{bdir}/sim", faster], capture_output=True, text=True).stdout
            m = re.search(r"EXIT at frame (\d+)", r)
            verdict = f"FASTER: leaves on frame {m.group(1) if m else '?'} ({os.path.relpath(faster, ROOT)})"
        print(f"{room:8s} leaves on frame {u}; frames 1-{keep} fixed, leave by frame {u - 1}? {verdict} ({dt:.0f} s)",
              flush=True)
        results[room] = dict(u=u, keep=keep, found=found, seconds=round(dt), inputs=frames)
        json.dump(results, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main()
