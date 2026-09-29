#!/usr/bin/env python3
"""
chain_tas.py -- play the community TAS of Chapter 1 through the model room
after room, from a given room and entry state, as far as it goes.

    python3 tests/chain_tas.py [--from lvl_3b] [--entry ENTRY.h] [--map 1-ForsakenCity.bin] [--tas 1A.tas]

Each room's inputs must leave the room on exactly their last frame; the next
room then starts from the state the model gives her on entering it
(tools/chapter.py). Rooms are exported from the map (tools/import_map.py)
with the TAS's next room as the goal. The default start is lvl_3b, entered
where lvl_4 must leave her (tests/chain_3b_5.py: x = 50 with 220 px/s of wall
speed retention; every entry that works there gives the same exit), because
the model's lvl_4 does not match the game yet.
"""
import argparse, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from chapter import enter_room, exit_side, origin_of, read_state, tables, write_state  # noqa: E402
from make_room import parse  # noqa: E402
from solve import build, read_tas, sh  # noqa: E402


def sections(text, rooms):
    """room -> input lines (labels that are not rooms of the map, like #1SH0G, stay in their room)"""
    out, order, cur = {}, [], None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"#(\S+)", s)
        if m and m.group(1) in rooms:
            cur = m.group(1)
            out[cur] = []
            order.append(cur)
        elif cur and re.match(r"\d+", s):
            out[cur].append(s)
    for lines in out.values():
        while lines and re.fullmatch(r"\d+", lines[-1]):
            lines.pop()
    return out, order


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", default="lvl_3b")
    ap.add_argument("--entry", help="entry state for the first room (default: see above)")
    ap.add_argument("--map", default=os.path.join(ROOT, "1-ForsakenCity.bin"))
    ap.add_argument("--tas", default=os.path.join(ROOT, "recordings", "1A.tas"))
    ap.add_argument("--rooms", default=os.path.join(ROOT, "rooms", "vanilla"))
    a = ap.parse_args()

    listing = sh([sys.executable, f"{ROOT}/tools/import_map.py", a.map]).stdout
    map_rooms = set(re.findall(r"^\s+(\S+)\s+\d+x\d+\s+tiles", listing, re.M))
    secs, order = sections(open(a.tas).read(), map_rooms)
    work = os.path.join(ROOT, "build", "chain_tas")
    os.makedirs(work, exist_ok=True)
    k = order.index(a.start)
    entry = a.entry
    if not entry:
        entry = os.path.join(work, f"entry_{a.start}.h")
        e = read_state(os.path.join(ROOT, "build", "community_tas", "entry_lvl_4.h"))   # an up transition
        e.update(x=50, facing=1, dashAttackTimer=0, wallSpeedRetained=220.0, wallSpeedRetentionTimer=4)
        room = os.path.join(a.rooms, f"1a_{a.start}.txt")
        if not os.path.exists(room):
            sh([sys.executable, f"{ROOT}/tools/import_map.py", a.map, a.start, "--to", order[k + 1], "-o", room])
        e["y"] = len(parse(room)[0]) * 8 - 9
        write_state(e, entry, f"{a.start}, entered where lvl_4 must leave her")
    total = 0
    for i in range(k, len(order) - 1):
        name, nxt = order[i], order[i + 1]
        room = os.path.join(a.rooms, f"1a_{name}.txt")
        if not os.path.exists(room):
            r = sh([sys.executable, f"{ROOT}/tools/import_map.py", a.map, name, "--to", nxt, "-o", room])
            if r.returncode:
                sys.exit(r.stderr)
        notes = [l.strip("; \n") for l in open(room) if "NOT MODELLED" in l]
        bdir = os.path.join(work, name)
        build(room, bdir, entry)
        route = os.path.join(bdir, "route.tas")
        open(route, "w").write("\n".join(secs[name]) + "\n")
        n = len(read_tas(route))
        out = sh([f"{bdir}/sim", route]).stdout
        m = re.search(r"EXIT at frame (\d+)", out)
        got = int(m.group(1)) if m else None
        ok = got == n
        print(f"{name:8s} {n:4d} frames of inputs: leaves on frame {got if got else '-- never'}  "
              f"{'ok' if ok else 'DIFFERENT'}{'   (' + notes[0] + ')' if notes else ''}", flush=True)
        if not ok:
            last = out.strip().splitlines()[-1]
            print(f"         stops there: {last}")
            break
        total += n
        exit_h = os.path.join(bdir, "exit.h")
        sh([f"{bdir}/sim", "-s", str(n), exit_h, route])
        st = read_state(exit_h)
        nroom = os.path.join(a.rooms, f"1a_{nxt}.txt")
        if not os.path.exists(nroom) and i + 2 < len(order):
            sh([sys.executable, f"{ROOT}/tools/import_map.py", a.map, nxt, "--to", order[i + 2], "-o", nroom])
        if not os.path.exists(nroom):
            break
        rows, nrows = parse(room)[0], parse(nroom)[0]
        e = enter_room(st, exit_side(st, len(rows[0]) * 8, len(rows) * 8), origin_of(room), origin_of(nroom),
                       len(nrows[0]) * 8, len(nrows) * 8, tables(bdir))
        entry = os.path.join(work, f"entry_{nxt}.h")
        write_state(e, entry, f"entering {nxt} from {name}")
    print(f"{total} frames of the community TAS played exactly from {a.start}")


if __name__ == "__main__":
    main()
