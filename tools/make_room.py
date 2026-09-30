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
    ; zipmover X Y W H TX TY  a zip mover (W x H at (X, Y)) going to (TX, TY)
    ; fallingblock X Y W H CLIMBFALL  a falling block (W x H at (X, Y));
                            CLIMBFALL 1: climbing on it also sets it off
    ; crumble X Y W         a crumble block (W x 8 at (X, Y))
    ; dashblock X Y W H CANDASH  a dash block (W x H at (X, Y)); CANDASH 1: a
                            dash into it breaks it (and she rebounds)
Spikes touching a zip mover or falling block from outside (Spikes.IsRiding)
are attached to it and move with it.
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
    rows, exact, exits, ordered, jumpthrus, zipmovers, fallblocks, crumbles, dashblocks, dreamblocks = \
        [], None, [], [], [], [], [], [], [], []
    chaser = None
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
        elif line.startswith("; fallingblock "):
            fallblocks.append(tuple(int(v) for v in words[2:7]))
        elif line.startswith("; crumble "):
            crumbles.append(tuple(int(v) for v in words[2:5]))
        elif line.startswith("; dashblock "):
            dashblocks.append(tuple(int(v) for v in words[2:7]))
        elif line.startswith("; dreamblock "):
            dreamblocks.append(tuple(int(v) for v in words[2:6]))
        elif line.startswith("; chaser"):
            chaser = int(words[2]) if len(words) > 2 else 90
        if not line or line.startswith(";"):
            continue
        rows.append(line)
    w = len(rows[0])
    assert all(len(r) == w for r in rows), "all rows must have the same width"
    assert len(rows) <= 128, "rooms taller than 128 tiles need a wider column type"
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
    parse.fallblocks = fallblocks
    parse.crumbles = crumbles
    parse.dashblocks = dashblocks
    parse.dreamblocks = dreamblocks
    parse.chaser = chaser
    return rows, spawn, exits, tile_spikes + ordered, jumpthrus, zipmovers


def fallblocks_of(path):
    """the falling blocks of a room file: [(x, y, w, h, climbFall)]"""
    parse(path)
    return parse.fallblocks


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


# ---- falling blocks -------------------------------------------------------
FB_SHAKE = wait_updates(0.2)            # yield return 0.2f (shaking)
FB_WAIT = wait_updates(0.4)             # float timer = 0.4f; while (timer > 0 && PlayerWaitCheck())
FB_SHAKE_END = FB_SHAKE + 1             # fbT after the shake: the first PlayerWaitCheck update
FB_WAIT_END = FB_SHAKE_END + FB_WAIT    # the last update of the wait loop (timer <= 0 there)
FB_FALL0 = FB_WAIT_END + 1              # fbT after the first fall update


def tiles_hit(rows, x0, y0, x1, y1):
    """Grid.Collide(rect) against the room's tiles (outside the grid is air)"""
    for cy in range(max(0, y0 // 8), min(len(rows), (y1 - 1) // 8 + 1)):
        for cx in range(max(0, x0 // 8), min(len(rows[0]), (x1 - 1) // 8 + 1)):
            if rows[cy][cx] == "#":
                return True
    return False


def fall_cycle(x, y, w, h, rows, jumpthrus):
    """FallingBlock.Sequence() from the update that finds her: one entry per
    update (index = fbT after it): (y, pixels moved, LiftSpeed.Y). Ends with
    the update it lands on the tiles or a jump-through (MoveVCollideSolids
    returns true) or falls 16 px below the room (Collidable = false).
    Returns (entries, gone). Other moving solids are not in its way (checked
    by the caller)."""
    out = [(y, 0, 0.0)] * FB_FALL0
    py, speed, cy = y, 0.0, 0.0
    while True:
        speed = approach(speed, 160.0, f32(500.0 * DT32))       # Calc.Approach(speed, 160f, 500f * DeltaTime)
        mv = f32(speed * DT32)                                   # MoveVCollideSolids(speed * DeltaTime)
        ly = f32(mv / DT32)                                      # LiftSpeed.Y = moveV / DeltaTime
        cy = f32(cy + mv)
        num = round(cy)
        moved, hit = 0, False
        if num != 0:
            cy = f32(cy - num)
            step = 1 if num > 0 else -1
            while num != 0:                                      # MoveVExactCollideSolids
                ny = py + moved + step
                if tiles_hit(rows, x, ny, x + w, ny + h):
                    hit = True
                    break
                if num > 0 and any(jx0 < x + w and jx1 > x and jy < ny + h and jy + 5 > ny
                                   and not (jy < py + moved + h and jy + 5 > py + moved)
                                   for jx0, jy, jx1 in jumpthrus):
                    hit = True
                    break
                moved += step
                num -= step
        py += moved
        out.append((py, moved, ly))
        if hit:
            return out, False
        if py > len(rows) * 8 + 16:                              # Top > level.Bounds.Bottom + 16
            return out, True
        assert len(out) < 2000, "falling block never lands"


def spike_attached(c, solids):
    """Spikes.IsRiding(solid): CollideCheckOutside(solid, Position -+ 1 px
    towards the surface it sits on); the first solid (in load order) wins"""
    d, x, y, n = c[1:]
    x0, y0, x1, y1 = spike_box(d, x, y, n)
    dx, dy = {"up": (0, 1), "down": (0, -1), "left": (1, 0), "right": (-1, 0)}[d]
    for k, (sx, sy, sw, sh) in enumerate(solids):
        def over(ax, ay):
            return x0 + ax < sx + sw and x1 + ax > sx and y0 + ay < sy + sh and y1 + ay > sy
        if over(dx, dy) and not over(0, 0):
            return k
    return -1


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
            "typedef " + ("unsigned int" if h <= 32 else "unsigned long long" if h <= 64 else "unsigned __int128") + " room_col_t;",
            "static const room_col_t ROOM_COLS[ROOM_W] = {"]
    for cx in range(w):
        bits = sum(1 << cy for cy, r in enumerate(rows) if r[cx] == "#")
        if h <= 32:
            out.append(f"    0x{bits:08x}u,")
        elif h <= 64:
            out.append(f"    0x{bits:016x}ULL,")
        else:
            lo = bits & 0xFFFFFFFFFFFFFFFF
            hi = bits >> 64
            out.append(f"    (((unsigned __int128)0x{hi:016x}ULL << 64) | 0x{lo:016x}ULL),")
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
    fallblocks = parse.fallblocks
    crumbles, dashblocks = parse.crumbles, parse.dashblocks
    solids = ([(x, y, w_, h_) for x, y, w_, h_, _, _ in zipmovers] + [(x, y, w_, h_) for x, y, w_, h_, _ in fallblocks]
              + [(x, y, w_, 8) for x, y, w_ in crumbles] + [(x, y, w_, h_) for x, y, w_, h_, _ in dashblocks])
    if colliders and solids:
        att = [spike_attached(c, solids) if c[0] == "spikes" else -1 for c in colliders]
        out.append("/* spikes attached to a moving solid (zip movers first, then falling blocks): its index, or -1 */")
        out.append("static const signed char PCOL_MS[NPCOL] = { " + ", ".join(str(a) for a in att) + " };")
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
    out += ["", "/* falling blocks: { x, y, w, h, climbFall } and FallingBlock.Sequence() per update",
            " * (see fall_cycle and fb_update in celeste.c): y after the update, pixels moved, LiftSpeed.Y */",
            f"#define NFALLBLOCKS {len(fallblocks)}"]
    if fallblocks:
        cycles = []
        for k, (x, y, w_, h_, _) in enumerate(fallblocks):
            c, gone = fall_cycle(x, y, w_, h_, rows, jumpthrus)
            ylo, yhi = y, c[-1][0] + h_
            for m, (sx, sy, sw, sh) in enumerate(solids):
                if m != len(zipmovers) + k and sx < x + w_ and sx + sw > x and sy < yhi and sy + sh > ylo:
                    sys.exit(f"falling block at ({x},{y}) would run into another moving solid: not modelled")
            cycles.append((c, gone))
        tmax = max(len(c) - 1 for c, _ in cycles)
        out += [f"#define FB_SHAKE_END {FB_SHAKE_END}   /* fbT 1..{FB_SHAKE_END - 1}: shaking (0.2 s) */",
                f"#define FB_WAIT_END {FB_WAIT_END}    /* fbT {FB_SHAKE_END}..{FB_WAIT_END}: the 0.4 s wait while she is on it */",
                f"#define FB_FALL0 {FB_FALL0}       /* fbT after the first fall update */",
                f"#define FB_T_MAX {tmax}",
                "static const short FALLBLOCKS[NFALLBLOCKS][5] = {"]
        out += [f"    {{ {x}, {y}, {w_}, {h_}, {cf} }}," for x, y, w_, h_, cf in fallblocks]
        out.append("};")
        out.append("static const short FB_T_END[NFALLBLOCKS] = { " + ", ".join(str(len(c) - 1) for c, _ in cycles) + " };")
        out.append("static const bool FB_GONE[NFALLBLOCKS] = { " + ", ".join("1" if g else "0" for _, g in cycles) + " };")
        pad = lambda c: c + [c[-1][:1] + (0, 0.0)] * (tmax + 1 - len(c))
        out.append("static const short FB_Y[NFALLBLOCKS][FB_T_MAX + 1] = {")
        out += ["  {" + ",".join(str(e[0]) for e in pad(c)) + "}," for c, _ in cycles]
        out.append("};")
        out.append("static const signed char FB_MOVE[NFALLBLOCKS][FB_T_MAX + 1] = {")
        out += ["  {" + ",".join(str(e[1]) for e in pad(c)) + "}," for c, _ in cycles]
        out.append("};")
        out.append("static const float FB_LIFT[NFALLBLOCKS][FB_T_MAX + 1] = {")
        out += ["  {" + ",".join(f"{float(e[2]).hex()}f" for e in pad(c)) + "}," for c, _ in cycles]
        out.append("};")
    out += ["", "/* crumble blocks: { x, y, w } (8 px tall) and where CrumblePlatform.Sequence() is (crT) */",
            f"#define NCRUMBLES {len(crumbles)}"]
    if crumbles:
        shake, wait, back = wait_updates(0.2), wait_updates(0.4), wait_updates(2.0)
        top_chk = 1 + shake
        top_end = top_chk + wait
        climb0 = top_end + 1
        climb_end = climb0 + 3 * (shake + 1) + wait - 1
        gone0 = climb_end + 1
        gone_end = gone0 + back
        out += [f"#define CR_TOP_CHK {top_chk}     /* crT 1..{top_chk - 1}: shaking after she stood on it (0.2 s) */",
                f"#define CR_TOP_END {top_end}     /* crT {top_chk}..{top_end}: the 0.4 s while she stays on top */",
                f"#define CR_CLIMB0 {climb0}      /* crT {climb0}..{climb_end}: after she climbed it (3 x 0.2 s + 0.4 s) */",
                f"#define CR_CLIMB_END {climb_end}",
                f"#define CR_GONE0 {gone0}      /* crT {gone0}..{gone_end}: crumbled (2 s), then back once she is out of its way */",
                f"#define CR_GONE_END {gone_end}",
                "static const short CRUMBLES[NCRUMBLES][3] = {"]
        out += [f"    {{ {x}, {y}, {w_} }}," for x, y, w_ in crumbles]
        out.append("};")
    out += ["", "/* dash blocks: { x, y, w, h, canDash } */", f"#define NDASHBLOCKS {len(dashblocks)}"]
    assert len(dashblocks) <= 8, "at most 8 dash blocks (State.dbBroken is 8 bits)"
    if dashblocks:
        out.append("static const short DASHBLOCKS[NDASHBLOCKS][5] = {")
        out += [f"    {{ {x}, {y}, {w_}, {h_}, {c} }}," for x, y, w_, h_, c in dashblocks]
        out.append("};")
    dreamblocks = parse.dreamblocks
    out += ["", "/* dream blocks: { x, y, w, h } */", f"#define NDREAMBLOCKS {len(dreamblocks)}"]
    assert len(dreamblocks) <= 8, "at most 8 dream blocks"
    if dreamblocks:
        out.append("static const short DREAMBLOCKS[NDREAMBLOCKS][4] = {")
        out += [f"    {{ {x}, {y}, {w_}, {h_} }}," for x, y, w_, h_ in dreamblocks]
        out.append("};")
    if parse.chaser is not None:
        out += ["", "/* Badeline chaser */",
                "#define HAS_CHASER 1",
                f"#define CHASER_DELAY {parse.chaser}"]
    else:
        out += ["", "#define HAS_CHASER 0"]
    out += ["#endif", ""]
    open(dst, "w").write("\n".join(out))


if __name__ == "__main__":
    main()
