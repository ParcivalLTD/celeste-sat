#!/usr/bin/env python3
"""
next_room.py -- does a different ending of a room still let the TAS go on?

Plays ROUTE through ROOM (from the state tests/chain_tas.py entered it with),
enters the next room of the TAS as the game would (tools/chapter.py), and
plays the TAS's own inputs there: do they still leave it on their last frame?

    python3 tests/next_room.py lvl_4 build/chain_tas/lvl_4/ending_faster.tas

Run tests/chain_tas.py first.
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from chapter import enter_room, exit_side, origin_of, read_state, tables, write_state  # noqa: E402
from make_room import parse  # noqa: E402
from solve import build, read_tas  # noqa: E402
from tas_endings import ORDER  # noqa: E402


def main():
    room, route = sys.argv[1], os.path.abspath(sys.argv[2])
    nxt = ORDER[ORDER.index(room) + 1]
    work = os.path.join(ROOT, "build", "next_room", f"{room}_{nxt}")
    os.makedirs(work, exist_ok=True)
    bdir = os.path.join(ROOT, "build", "chain_tas", room)
    out = subprocess.run([f"{bdir}/sim", route], capture_output=True, text=True).stdout
    m = re.search(r"EXIT at frame (\d+)", out)
    if not m:
        sys.exit(f"{route} does not leave {room}")
    n = int(m.group(1))
    exit_h = os.path.join(work, "exit.h")
    subprocess.run([f"{bdir}/sim", "-s", str(n), exit_h, route], capture_output=True)
    st = read_state(exit_h)
    ra, rb = os.path.join(ROOT, "rooms", "vanilla", f"1a_{room}.txt"), os.path.join(ROOT, "rooms", "vanilla", f"1a_{nxt}.txt")
    rows_a, rows_b = parse(ra)[0], parse(rb)[0]
    e = enter_room(st, exit_side(st, len(rows_a[0]) * 8, len(rows_a) * 8), origin_of(ra), origin_of(rb),
                   len(rows_b[0]) * 8, len(rows_b) * 8, tables(bdir))
    entry = os.path.join(work, "entry.h")
    write_state(e, entry, f"entering {nxt} after {os.path.basename(route)}")
    tas_next = os.path.join(ROOT, "build", "chain_tas", nxt, "route.tas")
    nb = os.path.join(work, "b")
    build(rb, nb, entry)
    out = subprocess.run([f"{nb}/sim", tas_next], capture_output=True, text=True).stdout
    m2 = re.search(r"EXIT at frame (\d+)", out)
    u = len(read_tas(tas_next))
    print(f"{room}: leaves on frame {n} (the TAS: {len(read_tas(os.path.join(bdir, 'route.tas')))}), at x={st['x']} y={st['y']} "
          f"speed ({st['spdX']:.2f}, {st['spdY']:.2f}); enters {nxt} at x={e['x']} y={e['y']}")
    print(f"{nxt}: the TAS's {u} frames of inputs " +
          (f"leave on frame {m2.group(1)}" + ("  <== still works" if int(m2.group(1)) == u else "") if m2
           else "do not leave it: " + out.strip().splitlines()[-1]))


if __name__ == "__main__":
    main()
