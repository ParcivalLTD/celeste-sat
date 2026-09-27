#!/usr/bin/env python3
"""Convert an ASCII room into model/room.h.

Format (one character per 8x8 tile):
    #  solid tile
    .  air
    S  spawn (air; Madeline stands with her feet on the bottom edge of this tile)
    E  air, marks the exit opening (cosmetic: any open tile in the rightmost
       column is an exit, since leaving the room to the right = level transition)
Lines starting with ';' are comments. All rows must have the same width.
"""
import sys


def parse(path):
    rows, exact = [], None
    for line in open(path):
        line = line.rstrip("\n")
        if line.startswith("; spawn "):           # exact spawn in pixels (from import_map.py)
            exact = tuple(int(v) for v in line.split()[2:4])
        if not line or line.startswith(";"):
            continue
        rows.append(line)
    w = len(rows[0])
    assert all(len(r) == w for r in rows), "all rows must have the same width"
    assert len(rows) <= 32, "rooms taller than 32 tiles need a wider column type"
    spawn = None
    for cy, r in enumerate(rows):
        for cx, ch in enumerate(r):
            if ch == "S":
                spawn = (cx * 8 + 4, (cy + 1) * 8)
    if exact:
        spawn = exact
    assert spawn, "room needs an S"
    return rows, spawn


def main():
    src, dst = sys.argv[1], sys.argv[2]
    rows, (sx, sy) = parse(src)
    w, h = len(rows[0]), len(rows)
    out = [f"/* generated from {src} by tools/make_room.py */",
           "#ifndef ROOM_H_INCLUDED", "#define ROOM_H_INCLUDED",
           f"#define ROOM_W {w}", f"#define ROOM_H {h}",
           f"#define SPAWN_X {sx}", f"#define SPAWN_Y {sy}",
           "/* the room, for reference:"]
    out += [f"   {r}" for r in rows]
    out += ["*/",
            "/* ROOM_COLS[c]: bit r set when tile (c, r) is solid */",
            "static const unsigned ROOM_COLS[ROOM_W] = {"]
    for cx in range(w):
        bits = sum(1 << cy for cy, r in enumerate(rows) if r[cx] == "#")
        out.append(f"    0x{bits:08x}u,")
    out += ["};", "#endif", ""]
    open(dst, "w").write("\n".join(out))


if __name__ == "__main__":
    main()
