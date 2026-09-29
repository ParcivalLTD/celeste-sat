#!/usr/bin/env python3
"""
transition.py -- compute entry state for next room from previous room's exit state.
Usage:
    python tools/transition.py <exit.h> <prev_room.txt> <next_room.txt> <bdir_with_tables> <out_entry.h>
"""
import sys, os
from chapter import read_state, write_state, parse, exit_side, origin_of, enter_room, tables

def main():
    if len(sys.argv) < 6:
        print("Usage: python transition.py <exit.h> <prev_room.txt> <next_room.txt> <bdir_with_tables> <out_entry.h>")
        sys.exit(1)
        
    exit_h = sys.argv[1]
    prev_room = sys.argv[2]
    next_room = sys.argv[3]
    bdir = sys.argv[4]
    out_entry = sys.argv[5]
    
    st = read_state(exit_h)
    rows = parse(prev_room)[0]
    side = exit_side(st, len(rows[0]) * 8, len(rows) * 8)
    nrows = parse(next_room)[0]
    
    print(f"Exit side from {prev_room}: {side}")
    print(f"Prev origin: {origin_of(prev_room)}, Next origin: {origin_of(next_room)}")
    print(f"Next room size: {len(nrows[0]) * 8} x {len(nrows) * 8}")
    
    e = enter_room(st, side, origin_of(prev_room), origin_of(next_room),
                   len(nrows[0]) * 8, len(nrows) * 8, tables(bdir))
    write_state(e, out_entry, f"entering {os.path.basename(next_room)} from {os.path.basename(prev_room)}")
    print(f"Wrote {out_entry}:")
    print(f"  Pos: ({e['x']}, {e['y']})")
    print(f"  Spd: ({e['spdX']}, {e['spdY']})")
    print(f"  Dashes: {e['dashes']}, Stamina: {e['stamina']}")

if __name__ == "__main__":
    main()
