#!/usr/bin/env python3
"""
import_map.py -- read rooms from a Celeste map file (Content/Maps/*.bin).

    tools/import_map.py game/1-ForsakenCity.bin                 # list rooms
    tools/import_map.py game/1-ForsakenCity.bin 3 -o room.txt   # export room "3"
    tools/import_map.py game/1-ForsakenCity.bin lvl_2 --to lvl_3 -o room.txt

The export writes the ASCII room format (celeste_sat/room.py); see
celeste_sat/celeste_map.py for what is exported and how. Map files are part
of the game and are not in the repository: copy them from
<Celeste>/Content/Maps into game/.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat.celeste_map import export_room, listing  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map")
    ap.add_argument("room", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--to", action="append", metavar="ROOM",
                    help="the room(s) to finish in (default: any neighbour); "
                         "transitions into other rooms count as failing")
    a = ap.parse_args()
    if not a.room:
        print("\n".join(listing(a.map)))
        return
    text = export_room(a.map, a.room, a.out, a.to)
    print(f"wrote {a.out}" if a.out else text, end="\n" if a.out else "")


if __name__ == "__main__":
    main()
