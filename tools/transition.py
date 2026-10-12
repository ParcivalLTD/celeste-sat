#!/usr/bin/env python3
"""
transition.py -- the state she enters the next room with, from the state
she left the previous one in (what tools/chapter.py does between rooms).

    python3 tools/transition.py EXIT.h PREV_ROOM.txt NEXT_ROOM.txt BUILD_DIR OUT_ENTRY.h

EXIT.h is the exit state (`sim -s N EXIT.h route.tas`, N = the exit frame);
BUILD_DIR is any build of PREV_ROOM (for its timer tables). The rules are in
celeste_sat/transition.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat.state import read_state, tables, write_state  # noqa: E402
from celeste_sat.transition import entry_from_exit_state  # noqa: E402


def main():
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    exit_h, prev_room, next_room, bdir, out_entry = sys.argv[1:]
    e, side = entry_from_exit_state(read_state(exit_h), prev_room, next_room, tables(bdir))
    write_state(e, out_entry, f"entering {os.path.basename(next_room)} from {os.path.basename(prev_room)}")
    print(f"left {os.path.basename(prev_room)} through its {side} edge; wrote {out_entry}:")
    print(f"  position ({e['x']}, {e['y']}), speed ({e['spdX']:g}, {e['spdY']:g}), "
          f"dashes {e['dashes']}, stamina {e['stamina']:g}")


if __name__ == "__main__":
    main()
