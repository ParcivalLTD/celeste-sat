#!/usr/bin/env python3
"""
import_chapter2.py -- export the rooms of Chapter 2 (2-OldSite.bin) into rooms/vanilla/2a_*.txt.

    python3 tools/import_chapter2.py [--map PATH]

The map file is part of the game: by default it is looked for in game/, the
repository root and $CELESTE_DIR/Content/Maps (celeste_sat/paths.py).

Each room is exported with the next room of the A-side route as its goal.
Then EXIT_FIXES are applied: corrections to the exported exits that were
found by hand and that a plain re-export would otherwise silently undo.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat.celeste_map import export_room  # noqa: E402
from celeste_sat.paths import VANILLA, find_map  # noqa: E402

# (room, the rooms that count as its goal), in the order of the A-side
ROOMS = [
    ("lvl_start", ["lvl_0"]),
    ("lvl_0", ["lvl_1"]),
    ("lvl_1", ["lvl_d0"]),
    ("lvl_d0", ["lvl_d7"]),
    ("lvl_d7", ["lvl_d8"]),
    ("lvl_d8", ["lvl_d3"]),      # lvl_d3 is not exported yet (the room before the chase is not modelled)
    ("lvl_3", ["lvl_4"]),
    ("lvl_4", ["lvl_5"]),
    ("lvl_5", ["lvl_6"]),
    ("lvl_6", ["lvl_7"]),
    ("lvl_7", ["lvl_8"]),
    ("lvl_8", ["lvl_9"]),
    ("lvl_9", ["lvl_10"]),
    ("lvl_10", ["lvl_2"]),
    ("lvl_2", ["lvl_11"]),
    ("lvl_11", ["lvl_12b"]),
    ("lvl_12b", ["lvl_12"]),
    ("lvl_12", ["lvl_13"]),
    ("lvl_13", []),
]

# room -> {exported exit line: the line to use instead}. The export makes the
# whole shared edge with the goal room an exit; where only part of that edge
# leads anywhere useful, the goal is narrowed to it (commit 588c008):
#   lvl_9 -> lvl_10: the chute through the switch gate, x in [488, 512); leaving
#     further left (x = 257) put her inside lvl_10's rock.
#   lvl_10 -> lvl_2: the opening at x in [80, 112).
EXIT_FIXES = {
    "lvl_9": {"; exit down 256 576   (-> lvl_10)": "; exit down 488 512   (-> lvl_10)"},
    "lvl_10": {"; exit down 64 448   (-> lvl_2)": "; exit down 80 112   (-> lvl_2)"},
}


def apply_fixes(room, text):
    for old, new in EXIT_FIXES.get(room, {}).items():
        if old not in text:
            sys.exit(f"{room}: expected the exported line {old!r} to fix; the export changed, check EXIT_FIXES")
        text = text.replace(old, new)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", help="2-OldSite.bin (default: see above)")
    a = ap.parse_args()
    path = a.map or find_map("2-OldSite.bin")
    os.makedirs(VANILLA, exist_ok=True)
    for room, goals in ROOMS:
        out = os.path.join(VANILLA, f"2a_{room}.txt")
        text = apply_fixes(room, export_room(path, room, goals=goals or None))
        open(out, "w").write(text)
        missing = re.search(r"^; NOT MODELLED \(ignored\): (.*)$", text, re.M)
        print(f"wrote {out}" + (f"   (not modelled: {missing.group(1)})" if missing else ""))


if __name__ == "__main__":
    main()
