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

    python3 experiments/tas_endings.py [--k 10] [--timeout 1800] [--rooms lvl_4,lvl_5]

Run tests/chain_tas.py first. Results go to build/tas_endings.json.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat.build import dump_state, replay  # noqa: E402
from celeste_sat.cbmc import leave_within  # noqa: E402
from celeste_sat.community import CH1_ORDER as ORDER  # noqa: E402
from celeste_sat.paths import BUILD, ROOT  # noqa: E402
from celeste_sat.tas import read_tas, write_tas  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=10, help="frames at the end of the TAS's room left free (default 10)")
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--rooms", help="comma-separated rooms (default: all that tests/chain_tas.py played)")
    a = ap.parse_args()
    rooms = a.rooms.split(",") if a.rooms else ORDER
    out_path = os.path.join(BUILD, "tas_endings.json")
    results = json.load(open(out_path)) if os.path.exists(out_path) else {}
    for room in rooms:
        bdir = os.path.join(BUILD, "chain_tas", room)
        route = os.path.join(bdir, "route.tas")
        if not os.path.exists(route):
            print(f"{room}: not played by tests/chain_tas.py, skipped")
            continue
        u = replay(bdir, route)
        if not u:
            print(f"{room}: the TAS's inputs do not leave it in the model, skipped")
            continue
        keep = u - a.k
        start = f"ending_start_{keep}.h"
        dump_state(bdir, route, keep, os.path.join(bdir, start))
        try:
            found, frames, dt = leave_within(bdir, a.k - 1, start, a.timeout)
        except SystemExit:                          # CBMC killed (out of memory) or crashed
            found, frames, dt = None, None, 0.0
        verdict = "TIMEOUT" if found is None else "no"
        if found:                                   # replay the TAS's first frames + the solver's
            faster = os.path.join(bdir, "ending_faster.tas")
            write_tas(faster, read_tas(route)[:keep] + frames, [f"{room}: TAS frames 1-{keep}, then CBMC"])
            e = replay(bdir, faster)
            verdict = f"FASTER: leaves on frame {e if e else '?'} ({os.path.relpath(faster, ROOT)})"
        print(f"{room:8s} leaves on frame {u}; frames 1-{keep} fixed, leave by frame {u - 1}? {verdict} ({dt:.0f} s)",
              flush=True)
        results[room] = dict(u=u, keep=keep, found=found, seconds=round(dt), inputs=frames)
        json.dump(results, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main()
