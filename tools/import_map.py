#!/usr/bin/env python3
"""
import_map.py -- read rooms from a Celeste map file (Content/Maps/*.bin).

    tools/import_map.py 1-ForsakenCity.bin                 # list rooms
    tools/import_map.py 1-ForsakenCity.bin 3 -o room.txt   # export room "3"
    tools/import_map.py 1-ForsakenCity.bin lvl_2 --to lvl_3 -o room.txt

Celeste stores maps with its BinaryPacker: a string table, then a tree of
elements with typed attributes. Each room ("level") has pixel bounds and a
"solids" child whose text holds one character per 8x8 tile ('0' = air).

The export writes the ASCII format of tools/make_room.py: solid tiles, the
player spawn ("; spawn X Y", exact pixels), one "; exit" line per neighbouring
room (with --to, only the rooms named there are goals; the others become
"; leave" lines), spikes and springs as directives in the game's order (spikes
are also drawn as ^ v < >), and jump-throughs (drawn as - when tile-aligned).
Other entities are not modelled and are listed in a comment.
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
    ap.add_argument("--to", action="append", metavar="ROOM",
                    help="the room(s) to finish in (default: any neighbour); "
                         "transitions into other rooms count as failing")
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
    print(export(package, level, lv, a.out, a.to), end="")


SPIKES = {"spikesUp": ("up", "^"), "spikesDown": ("down", "v"),
          "spikesLeft": ("left", "<"), "spikesRight": ("right", ">")}
# entities that change nothing for the player's movement
# fakeWall: not a Solid (walked through, it fades); the others only look or talk
COSMETIC = {"wire", "lightbeam", "bgdecal", "fgdecal", "cliffside_flag", "flutterbird",
            "fakeWall", "bonfire", "memorial", "memorialTextController"}


def neighbour_ranges(level, all_levels):
    """[(side, from, to, name)]: the stretch of each edge that leads into another
    room, in this room's pixel coordinates (MapData.CanTransitionTo)."""
    x0, y0, x1, y1 = room_rect(level)
    out = []
    for other in all_levels:
        if other is level:
            continue
        a0, b0, a1, b1 = room_rect(other)
        name = other.attrs["name"]
        if a1 == x0 and b0 < y1 and b1 > y0: out.append(("left", b0 - y0, b1 - y0, name))
        if a0 == x1 and b0 < y1 and b1 > y0: out.append(("right", b0 - y0, b1 - y0, name))
        if b1 == y0 and a0 < x1 and a1 > x0: out.append(("up", a0 - x0, a1 - x0, name))
        if b0 == y1 and a0 < x1 and a1 > x0: out.append(("down", a0 - x0, a1 - x0, name))
    return out


def export(package, level, lv, path=None, goals=None):
    rows = [list(r) for r in tile_rows(level)]
    H, W = len(rows), len(rows[0])
    ents = entities(level)
    players = [e for e in ents if e.name == "player"]
    exits = neighbour_ranges(level, lv)
    head = [f"; room {level.attrs['name']} of {package} ({W}x{H} tiles), imported by tools/import_map.py",
            f"; origin {level.attrs['x']} {level.attrs['y']}   (world position of the room's top-left corner)"]
    ignored, cosmetic, lines = set(), set(), []

    def free(cells):
        return all(0 <= cx < W and 0 <= cy < H and rows[cy][cx] == "." for cx, cy in cells)

    for e in ents:                                   # in the map's order (= the game's)
        a = e.attrs
        if e.name in SPIKES:
            d, ch = SPIKES[e.name]
            n = a.get("width" if d in ("up", "down") else "height", 8)
            lines.append(f"; spikes {d} {a['x']} {a['y']} {n}")
            if a["x"] % 8 == 0 and a["y"] % 8 == 0 and n % 8 == 0:
                x, y = a["x"] // 8, a["y"] // 8
                cells = {"up": [(x + i, y - 1) for i in range(n // 8)], "down": [(x + i, y) for i in range(n // 8)],
                         "left": [(x - 1, y + i) for i in range(n // 8)], "right": [(x, y + i) for i in range(n // 8)]}[d]
                if free(cells):
                    for cx, cy in cells:
                        rows[cy][cx] = ch                # drawing only: the directive is what counts
        elif e.name == "jumpThru":
            x, y, w = a["x"], a["y"], a.get("width", 8)
            cells = [(x // 8 + i, y // 8) for i in range(w // 8)]
            if x % 8 == 0 and y % 8 == 0 and w % 8 == 0 and free(cells):
                for cx, cy in cells:
                    rows[cy][cx] = "-"
            else:
                lines.append(f"; jumpthru {x} {y} {w}")
        elif e.name == "spring":
            if a.get("playerCanUse", True):
                lines.append(f"; spring {a['x']} {a['y']}")
        elif e.name == "refill" and not a.get("twoDash", False) and not a.get("oneUse", False):
            lines.append(f"; refill {a['x']} {a['y']}")
        elif e.name == "zipMover":
            x, y, w, h = a["x"], a["y"], a.get("width", 16), a.get("height", 16)
            node = e.child("node")
            if node:
                lines.append(f"; zipmover {x} {y} {w} {h} {node.attrs['x']} {node.attrs['y']}")
            else:
                ignored.add(e.name)
        elif e.name == "dashBlock":
            lines.append(f"; dashblock {a['x']} {a['y']} {a.get('width', 8)} {a.get('height', 8)} "
                         f"{int(a.get('canDash', True))}")
        elif e.name == "crumbleBlock":
            lines.append(f"; crumble {a['x']} {a['y']} {a.get('width', 8)}")
        elif e.name == "fallingBlock":
            lines.append(f"; fallingblock {a['x']} {a['y']} {a.get('width', 8)} {a.get('height', 8)} "
                         f"{int(a.get('climbFall', True))}")
        elif e.name == "dreamBlock":
            lines.append(f"; dreamblock {a['x']} {a['y']} {a.get('width', 8)} {a.get('height', 8)}")
        elif e.name in ("badelineChaser", "badelineOldsite", "badelineBoss"):
            delay = int(round(float(a.get("chaseWait", 1.55)) * 60))
            lines.append(f"; chaser {delay}")
        elif e.name in ("player", "strawberry", "goldenBerry", "checkpoint") or e.name in COSMETIC:
            if e.name not in ("player",):
                cosmetic.add(e.name)
        else:
            ignored.add(e.name)

    if ignored:
        head.append("; NOT MODELLED (ignored): " + ", ".join(sorted(ignored)))
    if cosmetic:
        head.append("; no effect on movement: " + ", ".join(sorted(cosmetic)))
    for side, a0, b0, name in exits:
        goal = goals is None or name in goals
        head.append(f"; {'exit' if goal else 'leave'} {side} {a0} {b0}   (-> {name})")
    if not exits:
        head.append("; WARNING: no neighbouring room, so there is no way out")
    elif goals is not None and not any(name in goals for _, _, _, name in exits):
        head.append(f"; WARNING: none of {', '.join(goals)} is a neighbour of this room")
    head += lines

    if players:
        p = players[0]
        head.append(f"; spawn {p.attrs['x']} {p.attrs['y']}")
        sx, sy = p.attrs["x"] // 8, (p.attrs["y"] - 1) // 8
        if rows[sy][sx] == ".":
            rows[sy][sx] = "S"
    else:
        head.append("; WARNING: no player spawn in this room; put an S where Madeline should start")
    text = "\n".join(head + ["".join(r) for r in rows]) + "\n"
    if path:
        open(path, "w").write(text)
        return f"wrote {path}\n"
    return text


if __name__ == "__main__":
    main()
