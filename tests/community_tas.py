#!/usr/bin/env python3
"""
community_tas.py -- replay the community TAS of Chapter 1 through the model.

VampireFlower's Celeste TAS inputs (github.com/VampireFlower/CelesteTAS) are
checked against the real game: played in Celeste, they finish the chapter.
This downloads the Chapter 1 file at a fixed commit (it is not copied into
this repository), takes the inputs of the first rooms and plays them through
the model, one room after the other: the first from the spawn, each later
one from the state Madeline enters it with (tools/chapter.py). The model
agrees with the game only if every room's inputs leave that room on exactly
their last frame -- one frame early or late, or a different spot, and the
next room's inputs no longer work.

    python3 tests/community_tas.py [rooms/vanilla]

Needs the rooms exported from your game (tools/import_map.py) as
1a_lvl_1.txt, 1a_lvl_2.txt, ... in that folder.
"""
import os, re, subprocess, sys, tempfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from chapter import enter_room, exit_side, origin_of, read_state, tables, write_state  # noqa: E402
from make_room import parse  # noqa: E402
from solve import build, read_tas  # noqa: E402

URL = ("https://raw.githubusercontent.com/VampireFlower/CelesteTAS/"
       "098927faa0da3101bf9c2371f1e45d719c830821/1A.tas")
ROOMS = ["lvl_1", "lvl_2", "lvl_3", "lvl_4"]          # rooms tested against community TAS


def sections(text):
    """room name -> its input lines, without the idle frames of the transition at the end"""
    out, cur = {}, None
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"#\S", s):             # "#lvl_1": a label (CelesteTAS); "# text" is a comment
            cur = s[1:].strip()
            out[cur] = []
        elif cur and re.match(r"\d+", s):
            out[cur].append(s)
    for name, lines in out.items():
        while lines and re.fullmatch(r"\d+", lines[-1]):   # "  40": waiting out the room transition
            lines.pop()
    return out


def main():
    rdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "rooms", "vanilla")
    rooms = [os.path.join(rdir, f"1a_{r}.txt") for r in ROOMS]
    missing = [r for r in rooms if not os.path.exists(r)]
    if missing:
        sys.exit(f"missing {', '.join(missing)} -- export them with tools/import_map.py")
    tas = sections(urllib.request.urlopen(URL, timeout=30).read().decode("utf-8", "replace"))
    out = os.path.join(ROOT, "build", "community_tas")
    os.makedirs(out, exist_ok=True)
    entry, ok = None, True
    for i, (name, room) in enumerate(zip(ROOMS, rooms)):
        bdir = os.path.join(out, name)
        build(room, bdir, entry)
        route = os.path.join(bdir, "route.tas")
        open(route, "w").write("\n".join([f"# VampireFlower/CelesteTAS 1A.tas #{name}"] + tas[name]) + "\n")
        n = len(read_tas(route))
        r = subprocess.run([os.path.join(bdir, "sim"), route], capture_output=True, text=True)
        m = re.search(r"EXIT at frame (\d+)", r.stdout)
        got = int(m.group(1)) if m else None
        good = got == n
        ok &= good
        where = "spawn" if i == 0 else f"entered from {ROOMS[i - 1]}"
        print(f"{name}: {n} frames of inputs ({where}); model leaves the room on frame "
              f"{got if got else '-- never'}  {'ok' if good else 'DIFFERENT'}")
        if not good or i + 1 == len(ROOMS):
            break
        exit_h = os.path.join(bdir, "exit.h")
        subprocess.run([os.path.join(bdir, "sim"), "-s", str(n), exit_h, route], capture_output=True)
        st = read_state(exit_h)
        rows = parse(room)[0]
        nrows = parse(rooms[i + 1])[0]
        e = enter_room(st, exit_side(st, len(rows[0]) * 8, len(rows) * 8), origin_of(room),
                       origin_of(rooms[i + 1]), len(nrows[0]) * 8, len(nrows) * 8, tables(bdir))
        entry = os.path.join(out, f"entry_{ROOMS[i + 1]}.h")
        write_state(e, entry, f"entering {ROOMS[i + 1]} from {name}")
    print("MATCH" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
