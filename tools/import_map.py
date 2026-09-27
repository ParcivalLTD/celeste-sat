#!/usr/bin/env python3
"""
import_map.py -- read rooms from a Celeste map file (Content/Maps/*.bin).

    tools/import_map.py 1-ForsakenCity.bin                 # list rooms
    tools/import_map.py 1-ForsakenCity.bin 3 -o room.txt   # export room "3"

Celeste stores maps with its BinaryPacker: a string table, then a tree of
elements with typed attributes. Each room ("level") has pixel bounds and a
"solids" child whose text holds one character per 8x8 tile ('0' = air).

The export writes the ASCII format of tools/make_room.py. The model knows
only solid tiles, so entities (spikes, springs, jump-throughs, ...) are
listed as warnings. The player spawn becomes "; spawn X Y" (exact pixels).
The exit is the right edge, which is what the model supports; for rooms left
another way the export says so.
"""
import argparse, struct, sys


class Reader:
    def __init__(self, data):
        self.d, self.p = data, 0

    def take(self, n):
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def u8(self): return self.take(1)[0]
    def i16(self): return struct.unpack("<h", self.take(2))[0]
    def i32(self): return struct.unpack("<i", self.take(4))[0]
    def f32(self): return struct.unpack("<f", self.take(4))[0]

    def string(self):                       # C# BinaryReader.ReadString: 7-bit length prefix + UTF-8
        n, shift = 0, 0
        while True:
            b = self.u8()
            n |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                break
        return self.take(n).decode("utf-8")


class Element:
    def __init__(self, name):
        self.name, self.attrs, self.children = name, {}, []

    def child(self, name):
        return next((c for c in self.children if c.name == name), None)


def read_map(path):
    r = Reader(open(path, "rb").read())
    header = r.string()
    if header != "CELESTE MAP":
        sys.exit(f"{path}: not a Celeste map (header {header!r})")
    package = r.string()
    lookup = [r.string() for _ in range(r.i16())]

    def element():
        e = Element(lookup[r.i16()])
        for _ in range(r.u8()):
            key = lookup[r.i16()]
            t = r.u8()
            if t == 0: v = bool(r.u8())
            elif t == 1: v = r.u8()
            elif t == 2: v = r.i16()
            elif t == 3: v = r.i32()
            elif t == 4: v = r.f32()
            elif t == 5: v = lookup[r.i16()]
            elif t == 6: v = r.string()
            elif t == 7:                         # run-length encoded string: (count, char) pairs
                raw = r.take(r.i16())
                v = "".join(chr(raw[i + 1]) * raw[i] for i in range(0, len(raw), 2))
            elif t == 8: v = struct.unpack("<q", r.take(8))[0]
            elif t == 9: v = struct.unpack("<d", r.take(8))[0]
            else:
                sys.exit(f"unknown attribute type {t} at offset {r.p}")
            e.attrs[key] = v
        for _ in range(r.i16()):
            e.children.append(element())
        return e

    return package, element()


def rooms(root):
    levels = root.child("levels")
    return levels.children if levels else []


def tile_rows(level):
    w, h = level.attrs["width"] // 8, level.attrs["height"] // 8
    solids = level.child("solids")
    text = solids.attrs.get("innerText", "") if solids else ""
    lines = text.replace("\r", "").split("\n")
    rows = []
    for y in range(h):
        line = lines[y] if y < len(lines) else ""
        rows.append("".join("#" if x < len(line) and line[x] not in "0 " else "." for x in range(w)))
    return rows


def entities(level):
    ents = level.child("entities")
    return ents.children if ents else []


def room_rect(level):
    a = level.attrs
    return a["x"], a["y"], a["x"] + a["width"], a["y"] + a["height"]


def neighbours(level, all_levels):
    """Which edges of this room touch another room: {'left': [...], 'right': [...], ...}"""
    x0, y0, x1, y1 = room_rect(level)
    out = {"left": [], "right": [], "up": [], "down": []}
    for other in all_levels:
        if other is level:
            continue
        a0, b0, a1, b1 = room_rect(other)
        name = other.attrs["name"]
        if a1 == x0 and b0 < y1 and b1 > y0: out["left"].append(name)
        if a0 == x1 and b0 < y1 and b1 > y0: out["right"].append(name)
        if b1 == y0 and a0 < x1 and a1 > x0: out["up"].append(name)
        if b0 == y1 and a0 < x1 and a1 > x0: out["down"].append(name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("room", nargs="?")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()

    package, root = read_map(a.map)
    lv = rooms(root)
    if not a.room:
        print(f"{package}: {len(lv)} rooms")
        for l in lv:
            at = l.attrs
            kinds = {}
            for e in entities(l):
                kinds[e.name] = kinds.get(e.name, 0) + 1
            nb = neighbours(l, lv)
            exits = " ".join(f"{k}:{','.join(v)}" for k, v in nb.items() if v)
            ents = ", ".join(f"{k}x{n}" if n > 1 else k for k, n in sorted(kinds.items()))
            print(f"  {at['name']:>8}  {at['width'] // 8:3d}x{at['height'] // 8:<3d} tiles  [{exits}]  {ents}")
        return

    level = next((l for l in lv if l.attrs["name"] == a.room), None)
    if level is None:
        sys.exit(f"no room named {a.room!r}")
    rows = tile_rows(level)
    ents = entities(level)
    players = [e for e in ents if e.name == "player"]
    others = sorted({e.name for e in ents if e.name != "player"})
    nb = neighbours(level, lv)
    out = [f"; room {level.attrs['name']} of {package} ({len(rows[0])}x{len(rows)} tiles), imported by tools/import_map.py",
           f"; neighbours: " + ", ".join(f"{k} -> {'/'.join(v)}" for k, v in nb.items() if v)]
    if others:
        out.append("; NOT MODELLED (ignored): " + ", ".join(others))
    if not nb["right"]:
        out.append("; WARNING: no room to the right; the model can only solve exits through the right edge")
    if players:
        p = players[0]
        out.append(f"; spawn {p.attrs['x']} {p.attrs['y']}")
        sx, sy = p.attrs["x"] // 8, (p.attrs["y"] - 1) // 8
        r = list(rows[sy]); r[sx] = "S"; rows[sy] = "".join(r)
    else:
        out.append("; WARNING: no player spawn in this room; put an S where Madeline should start")
    out += rows
    text = "\n".join(out) + "\n"
    if a.out:
        open(a.out, "w").write(text)
        print(f"wrote {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
