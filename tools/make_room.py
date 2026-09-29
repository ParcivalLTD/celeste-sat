#!/usr/bin/env python3
"""Convert an ASCII room into room.h for the model.

Format (one character per 8x8 tile):
    #  solid tile
    .  air
    S  spawn (air; Madeline stands with her feet on the bottom edge of this tile)
    E  air (cosmetic marker for an exit opening)
    ^  air with spikes pointing up along the bottom of this tile (on a floor)
    v  air with spikes pointing down along the top of this tile (on a ceiling)
    <  air with spikes pointing left along the right side of this tile (on a wall)
    >  air with spikes pointing right along the left side of this tile (on a wall)
    -  air with a jump-through platform along the top of this tile

Lines starting with ';' are comments, except these directives:
    ; spawn X Y             exact spawn in pixels (overrides S)
    ; exit SIDE FROM TO     a neighbouring room on SIDE (left, right, up, down)
                            covering pixels [FROM, TO) along that edge; leaving
                            the room there is the goal. Without any exit line
                            the whole right edge is the exit.
    ; leave SIDE FROM TO    a neighbouring room that is not the goal: going
                            there counts as failing (like dying)
    ; spikes DIR X Y LEN    spikes in the game's entity coordinates (DIR up,
                            down, left, right; LEN is the width for up/down,
                            the height for left/right). A directive replaces
                            spike characters drawn on the same tiles.
    ; jumpthru X Y W        a jump-through platform, top edge at Y, x in [X, X+W)
    ; spring X Y            a floor spring whose base centre is at (X, Y)
    ; refill X Y            a dash refill crystal centred at (X, Y)
Spikes and springs act in the order they are listed (the game checks them in
that order within a frame); spikes drawn with characters come first.
All rows must have the same width.
"""
import math, struct, sys

SIDES = {"left": 0, "right": 1, "up": 2, "down": 3}
DIRS = {"up": 0, "down": 1, "left": 2, "right": 3}
TILE_SPIKES = {"^": "up", "v": "down", "<": "left", ">": "right"}


def spike_box(d, x, y, n):
    """Spikes.cs hitboxes: up (n,3) at (0,-3); down (n,3); left (3,n) at (-3,0); right (3,n)."""
    if d == "up":    return (x, y - 3, x + n, y)
    if d == "down":  return (x, y, x + n, y + 3)
    if d == "left":  return (x - 3, y, x, y + n)
    return (x, y, x + 3, y + n)


def spike_cells(d, x, y, n):
    """Tiles that a tile-aligned spike strip would be drawn on (or None)."""
    if x % 8 or y % 8 or n % 8:
        return None
    if d == "up":    return {(x // 8 + i, y // 8 - 1) for i in range(n // 8)}
    if d == "down":  return {(x // 8 + i, y // 8) for i in range(n // 8)}
    if d == "left":  return {(x // 8 - 1, y // 8 + i) for i in range(n // 8)}
    return {(x // 8, y // 8 + i) for i in range(n // 8)}


def parse(path):
    """-> rows, spawn, exits [(side, a, b, goal)], colliders, jumpthrus [(x0, y, x1)]
    colliders: [("spikes", dir, x, y, len) | ("spring", x, y) | ("refill", x, y)] in game order."""
    rows, exact, exits, ordered, jumpthrus, zipmovers = [], None, [], [], [], []
    for line in open(path):
        line = line.rstrip("\n")
        words = line.split()
        if line.startswith("; spawn "):
            exact = tuple(int(v) for v in words[2:4])
        elif line.startswith("; exit ") or line.startswith("; leave "):
            side, a, b = words[2], int(words[3]), int(words[4])
            assert side in SIDES, f"unknown exit side {side!r}"
            exits.append((side, a, b, words[1] == "exit"))
        elif line.startswith("; spikes "):
            d, x, y, n = words[2], int(words[3]), int(words[4]), int(words[5])
            assert d in DIRS, f"unknown spike direction {d!r}"
            ordered.append(("spikes", d, x, y, n))
        elif line.startswith("; spring "):
            ordered.append(("spring", int(words[2]), int(words[3])))
        elif line.startswith("; refill "):
            ordered.append(("refill", int(words[2]), int(words[3])))
        elif line.startswith("; jumpthru "):
            x, y, w = int(words[2]), int(words[3]), int(words[4])
            jumpthrus.append((x, y, x + w))
        elif line.startswith("; zipmover "):
            x, y, w, h, tx, ty = int(words[2]), int(words[3]), int(words[4]), int(words[5]), int(words[6]), int(words[7])
            zipmovers.append((x, y, w, h, tx, ty))
        if not line or line.startswith(";"):
            continue
        rows.append(line)
    w = len(rows[0])
    assert all(len(r) == w for r in rows), "all rows must have the same width"
    assert len(rows) <= 64, "rooms taller than 64 tiles need a wider column type"
    spawn = None
    for cy, r in enumerate(rows):
        for cx, ch in enumerate(r):
            if ch == "S":
                spawn = (cx * 8 + 4, (cy + 1) * 8)
    if exact:
        spawn = exact
    assert spawn, "room needs an S"
    if not exits:
        exits = [("right", 0, len(rows) * 8, True)]

    # tiles already covered by spike directives (their characters are only a drawing)
    covered = set()
    for c in ordered:
        if c[0] == "spikes":
            cells = spike_cells(*c[1:])
            if cells:
                covered |= {(cx, cy, c[1]) for cx, cy in cells}

    def drawn(cx, cy, ch):
        return rows[cy][cx] == ch and (cx, cy, TILE_SPIKES[ch]) not in covered

    tile_spikes = []
    for cy, r in enumerate(rows):                       # ^ v: horizontal runs
        cx = 0
        while cx < w:
            ch = r[cx]
            if ch in "^v" and drawn(cx, cy, ch):
                n = 1
                while cx + n < w and drawn(cx + n, cy, ch):
                    n += 1
                tile_spikes.append(("spikes", TILE_SPIKES[ch], cx * 8, (cy + 1) * 8 if ch == "^" else cy * 8, n * 8))
                cx += n
            else:
                cx += 1
    for cx in range(w):                                 # < >: vertical runs
        cy = 0
        while cy < len(rows):
            ch = rows[cy][cx]
            if ch in "<>" and drawn(cx, cy, ch):
                n = 1
                while cy + n < len(rows) and drawn(cx, cy + n, ch):
                    n += 1
                tile_spikes.append(("spikes", TILE_SPIKES[ch], (cx + 1) * 8 if ch == "<" else cx * 8, cy * 8, n * 8))
                cy += n
            else:
                cy += 1
    for cy, r in enumerate(rows):                       # - : jump-through runs
        cx = 0
        while cx < w:
            if r[cx] == "-":
                n = 1
                while cx + n < w and r[cx + n] == "-":
                    n += 1
                jt = (cx * 8, cy * 8, (cx + n) * 8)
                if jt not in jumpthrus:
                    jumpthrus.append(jt)
                cx += n
            else:
                cx += 1
    return rows, spawn, exits, tile_spikes + ordered, jumpthrus, zipmovers


# ---- zip movers --------------------------------------------------------------
# ZipMover.Sequence() (a Monocle Coroutine) replayed with the game's single
# precision: each C# float operation is rounded to float32 here (a double
# result of +, -, *, / on two floats rounds to the same float32).
def f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


DT32 = f32(0.0166667)                   # Engine.DeltaTime
PI_OVER_2 = f32(math.pi / 2)             # MathHelper.PiOver2


def approach(val, target, max_move):     # Calc.Approach
    return min(f32(val + max_move), target) if val <= target else max(f32(val - max_move), target)


def sine_in(t):                          # Ease.SineIn: -(float)Math.Cos(PiOver2 * t) + 1
    return f32(-f32(math.cos(f32(PI_OVER_2 * t))) + 1.0)


def lerp(a, b, t):                       # MathHelper.Lerp: a + (b - a) * t
    return f32(a + f32(f32(b - a) * t))


def wait_updates(seconds):               # Coroutine: waitTimer -= DeltaTime while > 0
    w, k = f32(seconds), 0
    while w > 0:
        w, k = f32(w - DT32), k + 1
    return k


def zip_cycle(x, y, tx, ty):
    """One run of ZipMover.Sequence() from the update that finds a rider.
    Returns one entry per update, index 0 = waiting (not started), 1 = the
    update that found the rider, ...: (pos_x, pos_y, move_x, move_y, lift_x, lift_y),
    where pos is the position after that update, move the whole pixels
    Platform.MoveH / MoveV moved it (and its riders) and lift its LiftSpeed
    (moveH / DeltaTime, moveV / DeltaTime) when that update called MoveTo."""
    px, py, cx, cy = x, y, 0.0, 0.0                 # Position (whole pixels) and movementCounter
    out = [(px, py, 0, 0, 0.0, 0.0)]                # 0: waiting for a rider

    def idle(n):
        for _ in range(n):
            out.append((px, py, 0, 0, 0.0, 0.0))

    def move_to(vx, vy):                            # Platform.MoveTo -> MoveH, MoveV
        nonlocal px, py, cx, cy
        mh = f32(vx - f32(px + cx))
        lx = f32(mh / DT32)
        cx = f32(cx + mh)
        nx = round(cx)                              # (int)Math.Round: ties to even
        cx = f32(cx - nx)
        px += nx
        mv = f32(vy - f32(py + cy))
        ly = f32(mv / DT32)
        cy = f32(cy + mv)
        ny = round(cy)
        cy = f32(cy - ny)
        py += ny
        out.append((px, py, nx, ny, lx, ly))

    idle(1)                                         # HasPlayerRider: ... yield return 0.1f
    idle(wait_updates(0.1))
    idle(1)                                         # at = 0; while: yield return null
    at = 0.0
    while True:                                     # to the target, 0.5 s
        at = approach(at, 1.0, f32(2.0 * DT32))
        p = sine_in(at)
        move_to(lerp(x, tx, p), lerp(y, ty, p))
        if not at < 1.0:
            break                                   # ... yield return 0.5f (same update)
    idle(wait_updates(0.5))
    idle(1)                                         # at = 0; while: yield return null
    at = 0.0
    while True:                                     # back to the start, 2 s
        at = approach(at, 1.0, f32(0.5 * DT32))
        p = sine_in(at)
        move_to(lerp(tx, x, p), lerp(ty, y, p))
        if not at < 1.0:
            break                                   # ... yield return 0.5f
    idle(wait_updates(0.5))
    # the next update is back at the top of while (true): it checks for a rider
    assert (px, py) == (x, y) and cx == 0.0 and cy == 0.0, "zip mover did not return exactly to its start"
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    rows, (sx, sy), exits, colliders, jumpthrus, zipmovers = parse(src)
    w, h = len(rows[0]), len(rows)
    out = [f"/* generated from {src} by tools/make_room.py */",
           "#ifndef ROOM_H_INCLUDED", "#define ROOM_H_INCLUDED",
           f"#define ROOM_W {w}", f"#define ROOM_H {h}",
           f"#define SPAWN_X {sx}", f"#define SPAWN_Y {sy}",
           "/* the room, for reference:"]
    out += [f"   {r}" for r in rows]
    out += ["*/",
            "/* ROOM_COLS[c]: bit r set when tile (c, r) is solid */",
            "typedef unsigned " + ("int" if h <= 32 else "long long") + " room_col_t;",
            "static const room_col_t ROOM_COLS[ROOM_W] = {"]
    for cx in range(w):
        bits = sum(1 << cy for cy, r in enumerate(rows) if r[cx] == "#")
        out.append(f"    0x{bits:08x}u," if h <= 32 else f"    0x{bits:016x}ULL,")
    out += ["};", "",
            "/* exits: { side, from, to, goal } -- a neighbouring room on SIDE covering",
            " * [from, to) along that edge; goal 0 means going there counts as failing */",
            "#define EXIT_SIDE_LEFT 0", "#define EXIT_SIDE_RIGHT 1",
            "#define EXIT_SIDE_UP 2", "#define EXIT_SIDE_DOWN 3",
            f"#define NEXITS {len(exits)}",
            "static const short EXITS[NEXITS][4] = {"]
    out += [f"    {{ EXIT_SIDE_{s.upper()}, {a}, {b}, {int(g)} }}," for s, a, b, g in exits]
    out += ["};", "",
            "/* player colliders in game order: { kind, a, b, c, d, e }",
            " *   spikes: { PC_SPIKES, direction, x0, y0, x1, y1 }, hitbox [x0,x1) x [y0,y1)",
            " *   spring: { PC_SPRING, x, y, 0, 0, 0 }, floor spring, hitbox [x-8,x+8) x [y-6,y)",
            " *   refill: { PC_REFILL, x, y, index, 0, 0 }, dash refill, hitbox [x-8,x+8) x [y-8,y+8) */",
            "#define SPIKE_UP 0", "#define SPIKE_DOWN 1", "#define SPIKE_LEFT 2", "#define SPIKE_RIGHT 3",
            "#define PC_SPIKES 0", "#define PC_SPRING 1", "#define PC_REFILL 2",
            f"#define NSPIKES {sum(1 for c in colliders if c[0] == 'spikes')}",
            f"#define NREFILLS {sum(1 for c in colliders if c[0] == 'refill')}",
            f"#define NPCOL {len(colliders)}"]
    if colliders:
        out.append("static const short PCOL[NPCOL][6] = {")
        for c in colliders:
            if c[0] == "spikes":
                d, x, y, n = c[1:]
                x0, y0, x1, y1 = spike_box(d, x, y, n)
                out.append(f"    {{ PC_SPIKES, SPIKE_{d.upper()}, {x0}, {y0}, {x1}, {y1} }},   /* {d} at ({x},{y}), {n} px */")
            elif c[0] == "refill":
                out.append(f"    {{ PC_REFILL, {c[1]}, {c[2]}, {sum(1 for d in colliders[:colliders.index(c)] if d[0] == 'refill')}, 0, 0 }},")
            else:
                out.append(f"    {{ PC_SPRING, {c[1]}, {c[2]}, 0, 0, 0 }},")
        out.append("};")
    out += ["", "/* jump-through platforms: { x0, top, x1 }, hitbox [x0,x1) x [top,top+5) */",
            f"#define NJUMPTHRUS {len(jumpthrus)}"]
    if jumpthrus:
        out.append("static const short JUMPTHRUS[NJUMPTHRUS][3] = {")
        out += [f"    {{ {a}, {b}, {c} }}," for a, b, c in jumpthrus]
        out.append("};")
    out += ["", "/* zip movers: { x, y, w, h, target x, target y } and ZipMover.Sequence() per update",
            " * (see zip_cycle): position after the update, pixels moved, LiftSpeed */",
            f"#define NZIPMOVERS {len(zipmovers)}"]
    if zipmovers:
        cycles = [zip_cycle(x, y, tx, ty) for x, y, _, _, tx, ty in zipmovers]
        n = len(cycles[0])
        assert all(len(c) == n for c in cycles)
        out.append(f"#define ZIP_T_END {n - 1}   /* after this update it waits for a rider again */")
        out.append("static const short ZIPMOVERS[NZIPMOVERS][6] = {")
        out += [f"    {{ {x}, {y}, {w}, {h}, {tx}, {ty} }}," for x, y, w, h, tx, ty in zipmovers]
        out.append("};")
        out.append("static const short ZIP_POS[NZIPMOVERS][ZIP_T_END + 1][2] = {")
        for c in cycles:
            out.append("  {" + ",".join(f"{{{e[0]},{e[1]}}}" for e in c) + "},")
        out.append("};")
        out.append("static const signed char ZIP_MOVE[NZIPMOVERS][ZIP_T_END + 1][2] = {")
        for c in cycles:
            out.append("  {" + ",".join(f"{{{e[2]},{e[3]}}}" for e in c) + "},")
        out.append("};")
        out.append("static const float ZIP_LIFT[NZIPMOVERS][ZIP_T_END + 1][2] = {")
        for c in cycles:
            out.append("  {" + ",".join(f"{{{float(e[4]).hex()}f,{float(e[5]).hex()}f}}" for e in c) + "},")
        out.append("};")
    out += ["#endif", ""]
    open(dst, "w").write("\n".join(out))


if __name__ == "__main__":
    main()
