"""
Room -> room.h, the header the C model is compiled with (one build per room).

Besides the tiles, exits and colliders, this replays the moving solids'
coroutines once, in the game's single precision, and writes their paths as
tables, so the model (and the SAT solver) sees a table lookup instead of
trigonometry: ZipMover.Sequence(), SwitchGate.Sequence(), FallingBlock.Sequence(),
and the timing constants of CrumblePlatform.Sequence().
"""
import math
import struct
import sys

from .paths import write_text
from .room import MAX_BARRIERS, MAX_DASH_BLOCKS, MAX_DREAM_BLOCKS, spike_box


# ---- single precision ------------------------------------------------------
# The coroutines are replayed with the game's single precision: each C# float
# operation is rounded to float32 here (a double result of +, -, *, / on two
# floats rounds to the same float32).
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


class _Platform:
    """Platform.MoveTo (-> MoveH, MoveV) in single precision, one table entry per
    update: (pos_x, pos_y, move_x, move_y, lift_x, lift_y), where pos is the
    position after the update, move the whole pixels it moved (and moved its
    riders) and lift its LiftSpeed (moveH / DeltaTime, moveV / DeltaTime) when
    that update called MoveTo. Entry 0 is "waiting, not started"."""

    def __init__(self, x, y):
        self.px, self.py, self.cx, self.cy = x, y, 0.0, 0.0   # Position (whole pixels) and movementCounter
        self.out = [(x, y, 0, 0, 0.0, 0.0)]

    def idle(self, n):
        for _ in range(n):
            self.out.append((self.px, self.py, 0, 0, 0.0, 0.0))

    def move_to(self, vx, vy):
        mh = f32(vx - f32(self.px + self.cx))
        lx = f32(mh / DT32)
        self.cx = f32(self.cx + mh)
        nx = round(self.cx)                          # (int)Math.Round: ties to even
        self.cx = f32(self.cx - nx)
        self.px += nx
        mv = f32(vy - f32(self.py + self.cy))
        ly = f32(mv / DT32)
        self.cy = f32(self.cy + mv)
        ny = round(self.cy)
        self.cy = f32(self.cy - ny)
        self.py += ny
        self.out.append((self.px, self.py, nx, ny, lx, ly))


def zip_cycle(x, y, tx, ty):
    """One run of ZipMover.Sequence() from the update that finds a rider: one
    entry per update (see _Platform), index 0 = waiting (not started), 1 = the
    update that found the rider, ..."""
    p = _Platform(x, y)
    p.idle(1)                                       # HasPlayerRider: ... yield return 0.1f
    p.idle(wait_updates(0.1))
    p.idle(1)                                       # at = 0; while: yield return null
    at = 0.0
    while True:                                     # to the target, 0.5 s
        at = approach(at, 1.0, f32(2.0 * DT32))
        e = sine_in(at)
        p.move_to(lerp(x, tx, e), lerp(y, ty, e))
        if not at < 1.0:
            break                                   # ... yield return 0.5f (same update)
    p.idle(wait_updates(0.5))
    p.idle(1)                                       # at = 0; while: yield return null
    at = 0.0
    while True:                                     # back to the start, 2 s
        at = approach(at, 1.0, f32(0.5 * DT32))
        e = sine_in(at)
        p.move_to(lerp(tx, x, e), lerp(ty, y, e))
        if not at < 1.0:
            break                                   # ... yield return 0.5f
    p.idle(wait_updates(0.5))
    # the next update is back at the top of while (true): it checks for a rider
    assert (p.px, p.py) == (x, y) and p.cx == 0.0 and p.cy == 0.0, "zip mover did not return exactly to its start"
    return p.out


def cube_out(t):                         # Ease.CubeOut = Invert(CubeIn): 1 - (1 - t)^3
    u = f32(1.0 - t)
    return f32(1.0 - f32(f32(u * u) * u))


def gate_cycle(x, y, nx, ny):
    """SwitchGate.Sequence() (from the game's code) from the update that finds
    Switch.Check(Scene) true, one entry per update like zip_cycle; index 0 =
    waiting. After the last entry it stays at its node.
        while (!Switch.Check(Scene)) yield return null;
        yield return 0.1f;
        StartShaking(0.5f);                         (drawing only)
        while (icon.Rate < 1f) { icon.Rate += Engine.DeltaTime * 2f; yield return null; }
        yield return 0.1f;
        Tween tween = Tween.Create(Oneshot, Ease.CubeOut, 2f, start: true);
        tween.OnUpdate = t => MoveTo(Vector2.Lerp(start, node, t.Eased));
        Add(tween);                                 (updates from the next frame on)
        yield return 1.8f; ...                      (particles only)
    Tween.Update: TimeLeft -= DeltaTime; Percent = 1 - Math.Max(0, TimeLeft) / Duration;
    Eased = Easer(Percent); OnUpdate; removed once TimeLeft <= 0."""
    p = _Platform(x, y)
    p.idle(1)                                       # Check() true: yield return 0.1f
    p.idle(wait_updates(0.1))
    rate = 0.0
    while rate < 1.0:                               # one update per loop pass (yield return null)
        rate = f32(rate + f32(DT32 * 2.0))
        p.idle(1)
    p.idle(1)                                       # Rate >= 1: yield return 0.1f
    p.idle(wait_updates(0.1))
    p.idle(1)                                       # Tween.Create, Add, yield return 1.8f
    left = f32(2.0)
    while True:                                     # the tween, one update per frame from the next
        left = f32(left - DT32)
        pct = f32(1.0 - f32(max(0.0, left) / 2.0))
        e = cube_out(pct)
        p.move_to(lerp(x, nx, e), lerp(y, ny, e))
        if left <= 0:
            break
    assert (p.px, p.py) == (nx, ny), "switch gate did not arrive at its node"
    return p.out


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


def render(room):
    """the text of room.h for a parsed Room"""
    rows, (sx, sy), exits, colliders = room.rows, room.spawn, room.exits, room.colliders
    jumpthrus, zipmovers = room.jumpthrus, room.zipmovers
    w, h = len(rows[0]), len(rows)
    out = [f"/* generated from {room.path} by tools/make_room.py */",
           "#ifndef ROOM_H_INCLUDED", "#define ROOM_H_INCLUDED",
           f"#define ROOM_W {w}", f"#define ROOM_H {h}",
           f"#define SPAWN_X {sx}", f"#define SPAWN_Y {sy}",
           *([f"#define SPAWN_FACING {room.facing}"] if room.facing else []),
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
    out += ["};", ""]
    out += _outside(room, w, h)
    out += ["/* exits: { side, from, to, goal } -- a neighbouring room on SIDE covering",
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
    fallblocks, crumbles, dashblocks = room.fallblocks, room.crumbles, room.dashblocks
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
    out += _zip_movers(room)
    out += _touch_switches(room)
    out += _falling_blocks(room, solids)
    out += _crumbles(room)
    out += ["", "/* dash blocks: { x, y, w, h, canDash } */", f"#define NDASHBLOCKS {len(dashblocks)}"]
    assert len(dashblocks) <= MAX_DASH_BLOCKS, "at most 8 dash blocks (State.dbBroken is 8 bits)"
    if dashblocks:
        out.append("static const short DASHBLOCKS[NDASHBLOCKS][5] = {")
        out += [f"    {{ {x}, {y}, {w_}, {h_}, {c} }}," for x, y, w_, h_, c in dashblocks]
        out.append("};")
    dreamblocks = room.dreamblocks
    out += ["", "/* dream blocks: { x, y, w, h } */", f"#define NDREAMBLOCKS {len(dreamblocks)}"]
    assert len(dreamblocks) <= MAX_DREAM_BLOCKS, "at most 8 dream blocks"
    if dreamblocks:
        out.append("static const short DREAMBLOCKS[NDREAMBLOCKS][4] = {")
        out += [f"    {{ {x}, {y}, {w_}, {h_} }}," for x, y, w_, h_ in dreamblocks]
        out.append("};")
    barriers = room.barriers
    out += ["", "/* invisible barriers: { x, y, w, h }; static, so they need no state */",
            f"#define NBARRIERS {len(barriers)}"]
    assert len(barriers) <= MAX_BARRIERS, "at most 8 invisible barriers"
    if barriers:
        out.append("static const short BARRIERS[NBARRIERS][4] = {")
        out += [f"    {{ {x}, {y}, {w_}, {h_} }}," for x, y, w_, h_ in barriers]
        out.append("};")
    if room.chaser is not None:
        out += ["", "/* Badeline chaser */",
                "#define HAS_CHASER 1",
                f"#define CHASER_DELAY {room.chaser}",
                f"#define NCHASERS {room.nchasers}   /* chaser i follows 0.4 s * i later */"]
    else:
        out += ["", "#define HAS_CHASER 0"]
    out += ["#endif", ""]
    return "\n".join(out)


def _zip_movers(room):
    zipmovers = room.zipmovers
    out = ["", "/* zip movers: { x, y, w, h, target x, target y } and ZipMover.Sequence() per update",
           " * (see zip_cycle): position after the update, pixels moved, LiftSpeed */",
           f"#define NZIPMOVERS {len(zipmovers)}"]
    if not zipmovers:
        return out
    cycles = [gate_cycle(x, y, tx, ty) if k else zip_cycle(x, y, tx, ty)
              for (x, y, _, _, tx, ty), k in zip(zipmovers, room.zipkinds)]
    n = max(len(c) for c in cycles)

    def pad(c):
        return c + [c[-1][:2] + (0, 0, 0.0, 0.0)] * (n - len(c))

    out.append(f"#define ZIP_T_END {n - 1}   /* the longest table (entries beyond a mover's own end repeat its last position) */")
    out.append("/* 0: zip mover (starts when ridden, returns, waits again); 1: switch gate (starts when every"
               " touch switch is on, then stays at its node) */")
    out.append("static const unsigned char ZIP_KIND[NZIPMOVERS] = { " + ", ".join(str(k) for k in room.zipkinds) + " };")
    out.append("static const short ZIP_END[NZIPMOVERS] = { " + ", ".join(str(len(c) - 1) for c in cycles) + " };")
    out.append("static const short ZIPMOVERS[NZIPMOVERS][6] = {")
    out += [f"    {{ {x}, {y}, {w}, {h}, {tx}, {ty} }}," for x, y, w, h, tx, ty in zipmovers]
    out.append("};")
    out.append("static const short ZIP_POS[NZIPMOVERS][ZIP_T_END + 1][2] = {")
    for c in cycles:
        out.append("  {" + ",".join(f"{{{e[0]},{e[1]}}}" for e in pad(c)) + "},")
    out.append("};")
    out.append("static const signed char ZIP_MOVE[NZIPMOVERS][ZIP_T_END + 1][2] = {")
    for c in cycles:
        out.append("  {" + ",".join(f"{{{e[2]},{e[3]}}}" for e in pad(c)) + "},")
    out.append("};")
    out.append("static const float ZIP_LIFT[NZIPMOVERS][ZIP_T_END + 1][2] = {")
    for c in cycles:
        out.append("  {" + ",".join(f"{{{float(e[4]).hex()}f,{float(e[5]).hex()}f}}" for e in pad(c)) + "},")
    out.append("};")
    return out


def _col_literal(bits, h):
    if h <= 32:
        return f"0x{bits:08x}u"
    if h <= 64:
        return f"0x{bits:016x}ULL"
    return f"(((unsigned __int128)0x{bits >> 64:016x}ULL << 64) | 0x{bits & 0xFFFFFFFFFFFFFFFF:016x}ULL)"


def _outside(room, w, h):
    """the map's solid tiles around the room (only for rooms that have any, so
    other rooms' room.h stay as they were)"""
    if not room.outside:
        return []
    from .room import OUTSIDE_COLS as C, OUTSIDE_ROWS as R
    assert R == 8, "OUT_ABOVE / OUT_BELOW are 8-bit masks"
    out = ["/* the map's solid tiles around the room (; outside, celeste_map.solid_grid):",
           f" * OUT_SIDE[k]: columns -{C}..-1 (k = 0..{C - 1}) and ROOM_W..ROOM_W+{C - 1} (k = {C}..{2 * C - 1}),",
           " *   rows 0..ROOM_H-1, bits as in ROOM_COLS;",
           f" * OUT_ABOVE[c + {C}]: bit j = row j - {R}; OUT_BELOW[c + {C}]: bit j = row ROOM_H + j;",
           f" *   c from -{C} to ROOM_W+{C - 1} */",
           "#define HAS_OUTSIDE 1",
           f"static const room_col_t OUT_SIDE[{2 * C}] = {{"]
    for cx in list(range(-C, 0)) + list(range(w, w + C)):
        out.append(f"    {_col_literal(sum(1 << cy for cy in range(h) if (cx, cy) in room.outside), h)},")
    out.append("};")
    for name, base in (("OUT_ABOVE", -R), ("OUT_BELOW", h)):
        masks = [sum(1 << j for j in range(R) if (cx, base + j) in room.outside) for cx in range(-C, w + C)]
        out.append(f"static const unsigned char {name}[ROOM_W + {2 * C}] = {{")
        for i in range(0, len(masks), 16):
            out.append("    " + ", ".join(f"0x{m:02x}" for m in masks[i:i + 16]) + ",")
        out.append("};")
    return out + [""]


def _touch_switches(room):
    touches = room.touches
    out = ["", "/* touch switches: { x, y } (a 16 x 16 box around it touches her hurtbox, see touch_update); all on = TS_ALL */",
           f"#define NTOUCH {len(touches)}"]
    if touches:
        out.append(f"#define TS_ALL {(1 << len(touches)) - 1}")
        out.append("static const short TOUCHSWITCHES[NTOUCH][2] = { "
                   + ", ".join(f"{{ {x}, {y} }}" for x, y in touches) + " };")
    return out


def _falling_blocks(room, solids):
    fallblocks, zipmovers = room.fallblocks, room.zipmovers
    out = ["", "/* falling blocks: { x, y, w, h, climbFall } and FallingBlock.Sequence() per update",
           " * (see fall_cycle and fb_update in celeste.c): y after the update, pixels moved, LiftSpeed.Y */",
           f"#define NFALLBLOCKS {len(fallblocks)}"]
    if not fallblocks:
        return out
    cycles = []
    for k, (x, y, w_, h_, _) in enumerate(fallblocks):
        c, gone = fall_cycle(x, y, w_, h_, room.rows, room.jumpthrus)
        ylo, yhi = y, c[-1][0] + h_
        for m, (sx, sy, sw, sh) in enumerate(solids):
            if m != len(zipmovers) + k and sx < x + w_ and sx + sw > x and sy < yhi and sy + sh > ylo:
                sys.exit(f"falling block at ({x},{y}) would run into another moving solid: not modelled")
        cycles.append((c, gone))
    tmax = max(len(c) - 1 for c, _ in cycles)

    def pad(c):
        return c + [c[-1][:1] + (0, 0.0)] * (tmax + 1 - len(c))

    out += [f"#define FB_SHAKE_END {FB_SHAKE_END}   /* fbT 1..{FB_SHAKE_END - 1}: shaking (0.2 s) */",
            f"#define FB_WAIT_END {FB_WAIT_END}    /* fbT {FB_SHAKE_END}..{FB_WAIT_END}: the 0.4 s wait while she is on it */",
            f"#define FB_FALL0 {FB_FALL0}       /* fbT after the first fall update */",
            f"#define FB_T_MAX {tmax}",
            "static const short FALLBLOCKS[NFALLBLOCKS][5] = {"]
    out += [f"    {{ {x}, {y}, {w_}, {h_}, {cf} }}," for x, y, w_, h_, cf in fallblocks]
    out.append("};")
    out.append("static const short FB_T_END[NFALLBLOCKS] = { " + ", ".join(str(len(c) - 1) for c, _ in cycles) + " };")
    out.append("static const bool FB_GONE[NFALLBLOCKS] = { " + ", ".join("1" if g else "0" for _, g in cycles) + " };")
    out.append("static const short FB_Y[NFALLBLOCKS][FB_T_MAX + 1] = {")
    out += ["  {" + ",".join(str(e[0]) for e in pad(c)) + "}," for c, _ in cycles]
    out.append("};")
    out.append("static const signed char FB_MOVE[NFALLBLOCKS][FB_T_MAX + 1] = {")
    out += ["  {" + ",".join(str(e[1]) for e in pad(c)) + "}," for c, _ in cycles]
    out.append("};")
    out.append("static const float FB_LIFT[NFALLBLOCKS][FB_T_MAX + 1] = {")
    out += ["  {" + ",".join(f"{float(e[2]).hex()}f" for e in pad(c)) + "}," for c, _ in cycles]
    out.append("};")
    return out


def _crumbles(room):
    crumbles = room.crumbles
    out = ["", "/* crumble blocks: { x, y, w } (8 px tall) and where CrumblePlatform.Sequence() is (crT) */",
           f"#define NCRUMBLES {len(crumbles)}"]
    if not crumbles:
        return out
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
    return out


def write(src, dst):
    """tools/make_room.py SRC DST"""
    from .room import parse
    write_text(dst, render(parse(src)))
