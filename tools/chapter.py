#!/usr/bin/env python3
"""
chapter.py -- solve rooms in sequence, each starting where the previous one
was left, as in a real run.

    python3 tools/chapter.py rooms/vanilla/1a_lvl_1.txt rooms/vanilla/1a_lvl_2.txt \\
        rooms/vanilla/1a_lvl_3.txt --out build/chapter1 [--polish] [--sat-tail 15]

For room 1 Madeline starts at the spawn. Every later room starts from the
state she enters it with (celeste_sat/transition.py, which documents the
room transition), and the route there is searched from that state. Rooms
need an "; origin X Y" line (tools/import_map.py writes one) so positions
can be carried over.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat.paths import BUILD, ROOT  # noqa: E402
from celeste_sat.tas import read_tas, write_tas  # noqa: E402
from celeste_sat.transition import next_entry  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rooms", nargs="+")
    ap.add_argument("--out", default=os.path.join(BUILD, "chapter"))
    ap.add_argument("--polish", action="store_true", help="polish each room's beam route")
    ap.add_argument("--sat-tail", type=int, default=0,
                    help="also prove each route's last N frames optimal (CBMC; 12-16 is practical)")
    ap.add_argument("--beam-width", type=int, default=100000)
    ap.add_argument("--routes", help="comma-separated routes to use instead of searching, one per room "
                                     "('-' = search), e.g. results/1a_lvl_1.tas,-,-")
    a = ap.parse_args()
    given = (a.routes.split(",") if a.routes else []) + ["-"] * len(a.rooms)
    os.makedirs(a.out, exist_ok=True)

    entry, summary, all_frames = None, [], []
    for i, room in enumerate(a.rooms):
        name = os.path.splitext(os.path.basename(room))[0]
        rdir = os.path.join(os.path.abspath(a.out), name)
        cmd = [sys.executable, os.path.join(ROOT, "tools", "solve.py"), room, "--out", rdir,
               "--beam-width", str(a.beam_width), "--keep-exit"]
        if entry:
            cmd += ["--start", entry]
        if a.polish:
            cmd += ["--polish"]
        # first a route (no SAT), then optionally the SAT tail from that route
        if given[i] != "-":
            cmd += ["--tas", os.path.abspath(given[i])]
        r = subprocess.run(cmd + ["--no-sat"], capture_output=True, text=True)
        best = os.path.join(rdir, "best.tas")
        if r.returncode or not os.path.exists(best):
            sys.exit(f"{name}: no route found\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
        frames = read_tas(best)
        n = json.load(open(os.path.join(rdir, "result.json")))["frames"]
        proven = ""
        if a.sat_tail and n > a.sat_tail:
            route_copy = os.path.join(a.out, f"{name}_route.tas")
            write_tas(route_copy, frames[:n], [name])
            base = [c for c in cmd if c != "--polish"]
            if "--tas" in base:
                j = base.index("--tas"); del base[j:j + 2]
            r = subprocess.run(base + ["--tas", route_copy, "--from-frame", str(n - 1 - a.sat_tail)],
                               capture_output=True, text=True)
            res = json.load(open(os.path.join(rdir, "result.json")))
            n, frames = res["frames"], read_tas(best)
            proven = (f"; last {a.sat_tail} frames proven optimal" if res["proven"]
                      else "; SAT tail not finished")
        frames = frames[:n]
        all_frames.append(frames)
        start_note = "spawn" if i == 0 else f"entered from {os.path.basename(a.rooms[i - 1])}"
        print(f"{name}: {n} frames ({start_note}){proven}", flush=True)
        summary.append(dict(room=name, frames=n, start=start_note))

        if i + 1 == len(a.rooms):
            break
        # exit state -> entry state of the next room
        entry = os.path.join(os.path.abspath(a.out), f"entry_{i + 2}.h")
        e, _, _ = next_entry(rdir, best, n, room, a.rooms[i + 1], entry)
        print(f"   -> enters the next room at ({e['x']}, {e['y']}) with speed ({e['spdX']:g}, {e['spdY']:g})", flush=True)

    total = sum(s["frames"] for s in summary)
    combined = [f for fr in all_frames for f in fr]
    write_tas(os.path.join(a.out, "chapter.tas"), combined,
              [f"{len(summary)} rooms, {total} frames of control (transitions not counted)"] +
              [f"  {s['room']}: {s['frames']} frames" for s in summary])
    json.dump(dict(rooms=summary, total=total), open(os.path.join(a.out, "chapter.json"), "w"), indent=1)
    print(f"total: {total} frames ({total / 60:.2f} s) of control over {len(summary)} rooms")


if __name__ == "__main__":
    main()
