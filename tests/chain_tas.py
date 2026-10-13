#!/usr/bin/env python3
"""
chain_tas.py -- play the community TAS of Chapter 1 through the model, room
after room, from its first room, as far as it goes.

    python3 tests/chain_tas.py [--last ROOM] [--from ROOM --entry ENTRY.h] [--map MAP] [--tas 1A.tas]

This is the strongest check of the model there is: the community TAS has
been played in the real game, and a room's inputs only leave the room on
exactly their last frame if every frame before agreed with the game -- one
frame early or late, or a different spot, and the next room's inputs no
longer work. Each room starts from the state the model gives her on entering
it (celeste_sat/transition.py); the first from its spawn, unless --from names
a later room and --entry the state to enter it with.

Rooms are exported from the map (game/1-ForsakenCity.bin by default, see
celeste_sat/paths.py) into rooms/vanilla/1a_<room>.txt, with the TAS's next
room as the goal. The TAS is downloaded at a pinned commit
(celeste_sat/community.py) unless --tas gives a copy.

Leaves in build/chain_tas/: <room>/route.tas (the TAS's inputs for the room),
<room>/ (its build) and entry_<room>.h (the state she enters it with) --
the starting point of everything in experiments/ and hpc/.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat import community  # noqa: E402
from celeste_sat.build import build, exit_frame_of, run_sim  # noqa: E402
from celeste_sat.celeste_map import export_room, room_names  # noqa: E402
from celeste_sat.paths import BUILD, VANILLA, find_map  # noqa: E402
from celeste_sat.tas import read_tas, sections  # noqa: E402
from celeste_sat.transition import next_entry  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", default=None, help="first room to play (needs --entry)")
    ap.add_argument("--entry", help="entry state for the first room (default: its spawn)")
    ap.add_argument("--last", help="last room to play (default: as far as the TAS goes)")
    ap.add_argument("--map", help="1-ForsakenCity.bin (default: see celeste_sat/paths.py)")
    ap.add_argument("--tas", help="a copy of the community 1A.tas (default: download it at the pinned commit)")
    ap.add_argument("--rooms", default=VANILLA, help="where the exported rooms go (default rooms/vanilla)")
    a = ap.parse_args()

    map_path = a.map or find_map("1-ForsakenCity.bin")
    secs, order = sections(community.fetch("1A.tas", a.tas), room_names(map_path))
    work = os.path.join(BUILD, "chain_tas")
    os.makedirs(work, exist_ok=True)
    os.makedirs(a.rooms, exist_ok=True)

    def room_file(i):
        """rooms/vanilla/1a_<order[i]>.txt, exported with the next room as the goal if missing"""
        path = os.path.join(a.rooms, f"1a_{order[i]}.txt")
        if not os.path.exists(path) and i + 1 < len(order):
            export_room(map_path, order[i], path, [order[i + 1]])
        return path

    k = order.index(a.start) if a.start else 0
    entry = a.entry
    if k > 0 and not entry:
        sys.exit("--from a later room needs --entry")
    last = order.index(a.last) if a.last else len(order) - 2
    total = 0
    for i in range(k, min(last, len(order) - 2) + 1):
        name, nxt = order[i], order[i + 1]
        room = room_file(i)
        notes = [l.strip("; \n") for l in open(room) if "NOT MODELLED" in l]
        bdir = os.path.join(work, name)
        build(room, bdir, entry)
        route = os.path.join(bdir, "route.tas")
        open(route, "w").write("\n".join(secs[name]) + "\n")
        n = len(read_tas(route))
        out = run_sim(bdir, route).stdout
        got = exit_frame_of(out)
        ok = got == n
        print(f"{name:8s} {n:4d} frames of inputs: leaves on frame {got if got else '-- never'}  "
              f"{'ok' if ok else 'DIFFERENT'}{'   (' + notes[0] + ')' if notes else ''}", flush=True)
        if not ok:
            print(f"         stops there: {(out.strip().splitlines() or [''])[-1]}")
            print(f"MISMATCH after {total} frames of the community TAS played exactly from {order[k]}")
            return 1
        total += n
        nroom = room_file(i + 1)
        if not os.path.exists(nroom):
            break
        entry = os.path.join(work, f"entry_{nxt}.h")
        next_entry(bdir, route, n, room, nroom, entry, f"entering {nxt} from {name}")
    print(f"{total} frames of the community TAS played exactly from {order[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
