#!/usr/bin/env python3
"""
chain_3b_5.py -- the community TAS's lvl_3b and lvl_5, entered where lvl_4
must have left her (while the model's lvl_4 does not match the game).

The TAS's lvl_3b inputs leave lvl_3b on their last frame only from certain
entries (x, pending wall speed retention to the right). For each such entry
this plays lvl_3b (tests/scan_entry.c), groups the exit states, enters lvl_5
from each, and plays the TAS's lvl_5 inputs. If the lvl_3b exits agree,
lvl_5 gets its true entry, and lvl_5 (a zip mover going up) checks the zip
mover model against the TAS.

    python3 tests/chain_3b_5.py [rooms/vanilla] [1A.tas]
"""
import glob, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from chapter import enter_room, exit_side, origin_of, read_state, tables, write_state  # noqa: E402
from make_room import parse  # noqa: E402
from solve import build, read_tas, sh  # noqa: E402


def sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"#\S", s):
            cur = s[1:].strip()
            out[cur] = []
        elif cur and re.match(r"\d+", s):
            out[cur].append(s)
    for lines in out.values():
        while lines and re.fullmatch(r"\d+", lines[-1]):
            lines.pop()
    return out


def main():
    rdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "rooms", "vanilla")
    tas = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "recordings", "1A.tas")
    secs = sections(open(tas).read())
    r3b, r5 = os.path.join(rdir, "1a_lvl_3b.txt"), os.path.join(rdir, "1a_lvl_5.txt")
    work = os.path.join(ROOT, "build", "chain_3b_5")
    os.makedirs(work, exist_ok=True)
    route3b, route5 = os.path.join(work, "lvl_3b.tas"), os.path.join(work, "lvl_5.tas")
    open(route3b, "w").write("\n".join(secs["lvl_3b"]) + "\n")
    open(route5, "w").write("\n".join(secs["lvl_5"]) + "\n")
    n5 = len(read_tas(route5))

    b3b = os.path.join(work, "b3b")
    build(r3b, b3b)
    template = os.path.join(ROOT, "build", "community_tas", "entry_lvl_4.h")   # an up transition
    r = sh(["gcc", "-O2", f'-DSTART_STATE_FILE="{template}"', "-I", b3b, "-I", f"{ROOT}/model", "-I", f"{ROOT}/sim",
            "-o", f"{b3b}/scan", f"{ROOT}/tests/scan_entry.c"])
    if r.returncode:
        sys.exit(r.stderr)
    dumps = os.path.join(work, "exits")
    os.makedirs(dumps, exist_ok=True)
    for f in glob.glob(os.path.join(dumps, "*.h")):
        os.remove(f)
    print(sh([f"{b3b}/scan", route3b, dumps, "36", "60", "150", "295", "5"]).stdout.strip())
    groups = {}
    for f in sorted(glob.glob(os.path.join(dumps, "exit_*.h"))):
        body = "".join(l for l in open(f) if not l.startswith("/*"))
        m = re.search(r"exit_x(\d+)_r(\d+)", f)
        groups.setdefault(body, []).append((int(m.group(1)), int(m.group(2)), f))
    print(f"{len(groups)} different exit states from lvl_3b")
    rows3b, rows5 = parse(r3b)[0], parse(r5)[0]
    for i, entries in enumerate(groups.values()):
        st = read_state(entries[0][2])
        e5 = enter_room(st, exit_side(st, len(rows3b[0]) * 8, len(rows3b) * 8), origin_of(r3b), origin_of(r5),
                        len(rows5[0]) * 8, len(rows5) * 8, tables(b3b))
        ep5 = os.path.join(work, f"entry_5_{i}.h")
        write_state(e5, ep5, f"lvl_5 entry from lvl_3b exit #{i}")
        b5 = os.path.join(work, f"b5_{i}")
        build(r5, b5, ep5)
        out = sh([f"{b5}/sim", route5]).stdout
        m = re.search(r"EXIT at frame (\d+)", out)
        got = int(m.group(1)) if m else None
        xs = sorted(set(x for x, _, _ in entries))
        print(f"  exit #{i} ({len(entries)} entries, x {xs[0]}..{xs[-1]}): leaves lvl_3b at x={st['x']} "
              f"speed ({st['spdX']:.2f}, {st['spdY']:.2f}); enters lvl_5 at x={e5['x']}; the TAS's lvl_5 "
              f"({n5} frames) leaves on frame {got if got else '-- never'}{'  <== exact' if got == n5 else ''}")


if __name__ == "__main__":
    main()
