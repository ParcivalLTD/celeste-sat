#!/usr/bin/env python3
"""
next_room.py -- does a different ending of a room still let the TAS go on?

Plays ROUTE through ROOM (from the state tests/chain_tas.py entered it with),
enters the next room of the TAS as the game would (celeste_sat/transition.py), and
plays the TAS's own inputs there: do they still leave it on their last frame?

    python3 experiments/next_room.py lvl_4 build/chain_tas/lvl_4/ending_faster.tas

Run tests/chain_tas.py first.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat.build import build, replay, run_sim  # noqa: E402
from celeste_sat.community import CH1_ORDER as ORDER  # noqa: E402
from celeste_sat.paths import BUILD, VANILLA  # noqa: E402
from celeste_sat.tas import read_tas  # noqa: E402
from celeste_sat.transition import next_entry  # noqa: E402


def main():
    room, route = sys.argv[1], os.path.abspath(sys.argv[2])
    nxt = ORDER[ORDER.index(room) + 1]
    work = os.path.join(BUILD, "next_room", f"{room}_{nxt}")
    os.makedirs(work, exist_ok=True)
    bdir = os.path.join(BUILD, "chain_tas", room)
    n = replay(bdir, route)
    if not n:
        sys.exit(f"{route} does not leave {room}")
    ra, rb = os.path.join(VANILLA, f"1a_{room}.txt"), os.path.join(VANILLA, f"1a_{nxt}.txt")
    entry = os.path.join(work, "entry.h")
    e, st, _ = next_entry(bdir, route, n, ra, rb, entry, f"entering {nxt} after {os.path.basename(route)}",
                          exit_h=os.path.join(work, "exit.h"))
    tas_next = os.path.join(BUILD, "chain_tas", nxt, "route.tas")
    nb = os.path.join(work, "b")
    build(rb, nb, entry)
    out = run_sim(nb, tas_next).stdout
    m2 = replay(nb, tas_next)
    u = len(read_tas(tas_next))
    print(f"{room}: leaves on frame {n} (the TAS: {len(read_tas(os.path.join(bdir, 'route.tas')))}), at x={st['x']} y={st['y']} "
          f"speed ({st['spdX']:.2f}, {st['spdY']:.2f}); enters {nxt} at x={e['x']} y={e['y']}")
    print(f"{nxt}: the TAS's {u} frames of inputs " +
          (f"leave on frame {m2}" + ("  <== still works" if m2 == u else "") if m2
           else "do not leave it: " + out.strip().splitlines()[-1]))


if __name__ == "__main__":
    main()
