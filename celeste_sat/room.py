"""
The ASCII room format (rooms/*.txt) -> Room.

One character per 8x8 tile:
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
    ; origin X Y            world position of the room's top-left corner
                            (tools/import_map.py writes it; needed to carry
                            positions from one room into the next)
    ; spawn X Y [FACING]    exact spawn in pixels (overrides S); FACING -1: she
                            starts facing left
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
    ; switchgate X Y W H NX NY  a switch gate (W x H at (X, Y)); when every
                            touch switch in the room is on it moves to (NX, NY)
    ; touchswitch X Y       a touch switch centred at (X, Y)
    ; dreamblock X Y W H    a dream block (W x H at (X, Y))
    ; barrier X Y W H       an invisible barrier (W x H at (X, Y)): a Solid that
                            never moves and is never drawn
    ; chaser DELAY          a Badeline chaser (one line each; DELAY in frames)
    ; outside X0 X1 Y       solid tiles outside the room's grid: tile columns
                            X0..X1 of tile row Y, in the room's tile coordinates
                            (negative above and left of it). The game's tile grid
                            covers the whole map, and Celeste extends each room's
                            edge tiles outwards (celeste_map.solid_grid), so
                            outside is not simply air. The model reads OUTSIDE_COLS
                            columns either side and OUTSIDE_ROWS rows above and
                            below; without the directive everything outside is air.
Spikes touching a zip mover or falling block from outside (Spikes.IsRiding)
are attached to it and move with it.
Spikes and springs act in the order they are listed (the game checks them in
that order within a frame); spikes drawn with characters come first.
All rows must have the same width.
"""
import re
import sys
from dataclasses import dataclass, field

from .paths import read_text

SIDES = {"left": 0, "right": 1, "up": 2, "down": 3}
DIRS = {"up": 0, "down": 1, "left": 2, "right": 3}
TILE_SPIKES = {"^": "up", "v": "down", "<": "left", ">": "right"}
MAX_TOUCH_SWITCHES = 8            # model/celeste.h; State.tsOn is 8 bits
OUTSIDE_COLS, OUTSIDE_ROWS = 4, 8  # model/celeste.c (col_bits, above_bits, below_bits)
MAX_DASH_BLOCKS = 8               # State.dbBroken is 8 bits
MAX_DREAM_BLOCKS = 8
MAX_BARRIERS = 8
_ORIGIN = re.compile(r";\s*origin\s+(-?\d+)\s+(-?\d+)")


@dataclass
class Room:
    """A parsed room. Coordinates are pixels in the room unless noted."""
    path: str
    rows: list                                    # one string per tile row
    spawn: tuple                                  # (x, y) of her feet
    exits: list                                   # [(side, from, to, goal)]
    colliders: list                               # player colliders in game order:
                                                  # ("spikes", dir, x, y, len) | ("spring", x, y) | ("refill", x, y)
    jumpthrus: list                               # [(x0, top, x1)]
    zipmovers: list                               # [(x, y, w, h, tx, ty)]: zip movers and switch gates
    zipkinds: list                                # per zipmovers entry: 0 zip mover, 1 switch gate
    fallblocks: list = field(default_factory=list)   # [(x, y, w, h, climbFall)]
    crumbles: list = field(default_factory=list)     # [(x, y, w)]
    dashblocks: list = field(default_factory=list)   # [(x, y, w, h, canDash)]
    dreamblocks: list = field(default_factory=list)  # [(x, y, w, h)]
    barriers: list = field(default_factory=list)     # [(x, y, w, h)]
    touches: list = field(default_factory=list)      # touch switches [(x, y)]
    chaser: int = None                            # Badeline chaser delay (frames), or None
    nchasers: int = 0
    facing: int = None                            # spawn facing (-1: left), or None
    origin: tuple = None                          # world position of the top-left corner, or None
    outside: set = field(default_factory=set)     # solid tiles (cx, cy) outside the grid

    @property
    def width(self):                              # tiles
        return len(self.rows[0])

    @property
    def height(self):
        return len(self.rows)

    @property
    def width_px(self):
        return self.width * 8

    @property
    def height_px(self):
        return self.height * 8

    def require_origin(self):
        if self.origin is None:
            sys.exit(f"{self.path}: no '; origin X Y' line (re-export it with tools/import_map.py)")
        return self.origin


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


def _ints(words):
    return tuple(int(v) for v in words)


def parse(path):
    """read a room file (see the module docstring) -> Room"""
    rows, exact, exits, ordered, jumpthrus = [], None, [], [], []
    r = Room(path=path, rows=rows, spawn=None, exits=exits, colliders=[], jumpthrus=jumpthrus,
             zipmovers=[], zipkinds=[])
    for line in read_text(path).splitlines():
        words = line.split()
        if line.startswith("; spawn "):
            exact = _ints(words[2:4])
            if len(words) > 4 and words[4].lstrip("-").isdigit():
                r.facing = int(words[4])                 # ; spawn X Y FACING (-1: facing left)
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
            x, y, w = _ints(words[2:5])
            jumpthrus.append((x, y, x + w))
        elif line.startswith("; zipmover "):
            r.zipmovers.append(_ints(words[2:8]))
            r.zipkinds.append(0)
        elif line.startswith("; switchgate "):
            r.zipmovers.append(_ints(words[2:8]))      # a moving solid like a zip mover, kind 1
            r.zipkinds.append(1)
        elif line.startswith("; touchswitch "):
            r.touches.append(_ints(words[2:4]))
        elif line.startswith("; fallingblock "):
            r.fallblocks.append(_ints(words[2:7]))
        elif line.startswith("; crumble "):
            r.crumbles.append(_ints(words[2:5]))
        elif line.startswith("; dashblock "):
            r.dashblocks.append(_ints(words[2:7]))
        elif line.startswith("; dreamblock "):
            r.dreamblocks.append(_ints(words[2:6]))
        elif line.startswith("; barrier "):
            r.barriers.append(_ints(words[2:6]))
        elif line.startswith("; outside "):
            a, b, cy = _ints(words[2:5])
            r.outside.update((cx, cy) for cx in range(a, b + 1))
        elif line.startswith("; chaser"):
            r.chaser = int(words[2]) if len(words) > 2 else 90
            r.nchasers += 1
        elif r.origin is None and _ORIGIN.match(line):
            m = _ORIGIN.match(line)
            r.origin = (int(m.group(1)), int(m.group(2)))
        if not line or line.startswith(";"):
            continue
        rows.append(line)
    w = len(rows[0])
    assert all(len(row) == w for row in rows), "all rows must have the same width"
    assert len(rows) <= 128, "rooms taller than 128 tiles need a wider column type"
    for cx, cy in r.outside:
        assert not (0 <= cx < w and 0 <= cy < len(rows)), f"; outside tile ({cx}, {cy}) is inside the room"
        assert -OUTSIDE_COLS <= cx < w + OUTSIDE_COLS and -OUTSIDE_ROWS <= cy < len(rows) + OUTSIDE_ROWS, \
            f"; outside tile ({cx}, {cy}) is beyond the {OUTSIDE_COLS} x {OUTSIDE_ROWS} tiles the model reads"
    for cy, row in enumerate(rows):
        for cx, ch in enumerate(row):
            if ch == "S":
                r.spawn = (cx * 8 + 4, (cy + 1) * 8)
    if exact:
        r.spawn = exact
    assert r.spawn, "room needs an S"
    if not exits:
        exits.append(("right", 0, len(rows) * 8, True))

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
    for cy, row in enumerate(rows):                     # ^ v: horizontal runs
        cx = 0
        while cx < w:
            ch = row[cx]
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
    for cy, row in enumerate(rows):                     # - : jump-through runs
        cx = 0
        while cx < w:
            if row[cx] == "-":
                n = 1
                while cx + n < w and row[cx + n] == "-":
                    n += 1
                jt = (cx * 8, cy * 8, (cx + n) * 8)
                if jt not in jumpthrus:
                    jumpthrus.append(jt)
                cx += n
            else:
                cx += 1
    r.colliders = tile_spikes + ordered
    assert len(r.touches) <= MAX_TOUCH_SWITCHES, "at most 8 touch switches (State.tsOn is 8 bits)"
    assert not r.touches or 1 in r.zipkinds, "touch switches without a switch gate"
    return r


def origin_of(path):
    """the room's '; origin X Y' (exits if it has none)"""
    return parse(path).require_origin()
