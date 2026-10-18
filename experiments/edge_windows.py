#!/usr/bin/env python3
"""
edge_windows.py -- which window proofs of the Chapter 1 certificate can the
tiles outside the rooms (`; outside`) change?

    python3 experiments/edge_windows.py [--width 12] [--rooms lvl_1,...] [--json out.json]

The Leonardo windows (commit 9e3dd4f) were proven with everything outside a
room's grid as air. For Chapter 1 the outside tiles are the only model change
since then (the dream-block, chaser and touch-switch changes compile out), so
a window's "no" can only change if some input sequence in it makes a tile
check answer differently. A box check differs only when the box covers a
solid outside tile and no solid tile of the room; slip_check's points differ
when they land on a solid outside tile. Until the first such check the run is
the old model's, so where she can be is bounded by flooding the old model's
free space (tiles block, entity solids are left out, the ducking box):

- per frame at most VX px sideways (575 px/s: a duck hyper plus the lift
  boost cap, +5 corner corrections), VU up (290 px/s: a super wall jump with
  lift, +2 climb-up nudge), VD down (240 px/s, +3 floor snap, +3 with falling
  blocks), each plus the room's fastest zip mover (pi * distance px/s), as a
  horizontal then a vertical sweep or the other order;
- the probes: her box (h 6, 11 or 17) at dx in [-5, 5], dy in [-6, 4].

Window K is flagged if for some free frame t the forward flood from the
route's state after K frames (t frames) and the backward flood from its state
after K + W + 1 (W + 1 - t frames) meet at a position with a differing probe,
or if a differing position reached at t floods on to a room edge with an exit
within the remaining frames (leaving the room also ends a window). Unflagged
windows keep their Leonardo proof; flagged ones need tools/windows.py again.

2026-10-18, W = 12: 1,721 of 2,028 windows flagged (the bound is loose: no
gravity, every direction at full speed every frame).
"""
import argparse
import json
import math
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from celeste_sat.community import CH1_ORDER  # noqa: E402
from celeste_sat.room import parse  # noqa: E402
from celeste_sat.tas import read_tas  # noqa: E402

PX, PY0, PY1 = 5, -6, 4   # probe offsets: wall bounce 5, corner corrections, climb hop 6 up, ledge 4 down
M = 8


def trace(room):
    bdir = os.path.join(ROOT, "build", "chain_tas", room)
    out = os.path.join(bdir, "edge_trace.json")
    subprocess.run([os.path.join(bdir, "sim"), "-j", out, "route.tas"], cwd=bdir,
                   check=True, capture_output=True)
    return [(f["x"], f["y"]) for f in json.load(open(out))["frames"]]


def floor8(v):
    return v // 8


class Region:
    """her feet positions (x, y) in a room as one bitmask per row, x - X0 the bit"""

    def __init__(self, r, VX, VU, VD):
        self.pw, self.ph = len(r.rows[0]) * 8, len(r.rows) * 8
        self.X0, self.Y0, self.Y1 = -8, -24, self.ph + 24
        self.VX, self.VU, self.VD = VX, VU, VD
        solid = lambda cx, cy: 0 <= cy < len(r.rows) and 0 <= cx < len(r.rows[0]) and r.rows[cy][cx] == "#"
        out = r.outside
        rows = range(self.Y0, self.Y1)
        W8, H8 = len(r.rows[0]), len(r.rows)
        cache = {}

        def box_differs(c0, c1, r0, r1):
            # the new model's answer differs from the old one's (outside = air) only when the
            # box covers a solid outside tile and no solid tile of the room
            key = (c0, c1, r0, r1)
            if key not in cache:
                cells = [(cx, cy) for cx in {c0, c1} for cy in range(r0, r1 + 1)]
                cache[key] = any(c in out for c in cells) and not any(solid(*c) for c in cells)
            return cache[key]

        def differs(x, y):
            # only near the grid's edge can a probe reach outside it
            if 4 + PX + 4 <= x <= self.pw - 4 - PX - 4 and 17 + 6 + 2 < y < self.ph - 4 - 1:
                return False
            for h in (6, 11, 17):
                for dx in range(-PX, PX + 1):
                    for dy in range(PY0, PY1 + 1):
                        X, Y = x + dx, y + dy
                        if box_differs(floor8(X - 4), floor8(X + 3), floor8(Y - h), floor8(Y - 1)):
                            return True
            for h in (6, 11):                            # slip_check's points
                for px in (x + 4, x - 5):
                    for py in range(y - h - 2, y - h + 5):
                        c = (floor8(px), floor8(py))
                        if c in out:
                            return True
            return False

        self.free, self.touch, self.exit = [], [], []
        exit_sides = {e[0] for e in r.exits} or {"right"}
        for y in rows:
            f = t = e = 0
            for x in range(self.X0, self.pw + 9):
                b = 1 << (x - self.X0)
                # free in the old model (outside = air): the ducking box 8 x 6, inside the bounds clamps
                if (4 <= x <= self.pw - 4 and y >= -18 and y <= self.ph + 16
                        and not any(solid(cx, cy) for cx in (floor8(x - 4), floor8(x + 3))
                                    for cy in (floor8(y - 6), floor8(y - 1)))):
                    f |= b
                if differs(x, y):
                    t |= b
                if (("left" in exit_sides and x - 4 - M < 0) or ("right" in exit_sides and x + 4 + M > self.pw)
                        or ("up" in exit_sides and y - 11 - M < 0) or ("down" in exit_sides and y + M > self.ph)):
                    e |= b
            self.free.append(f)
            self.touch.append(t)
            self.exit.append(e)

    def point(self, x, y):
        S = [0] * len(self.free)
        S[y - self.Y0] = 1 << (x - self.X0)
        return S

    def _h(self, S):
        S = list(S)
        for _ in range(self.VX):
            S = [s | ((s << 1 | s >> 1) & f) for s, f in zip(S, self.free)]
        return S

    def _v1(self, S, d, n):
        """moves of up to n px in direction d (-1 up, +1 down), stopped by tiles"""
        m = len(S)
        for _ in range(n):
            S = [S[i] | ((S[i - d] if 0 <= i - d < m else 0) & self.free[i]) for i in range(m)]
        return S

    def _v(self, S, back):
        up, down = (self.VD, self.VU) if back else (self.VU, self.VD)
        a, b = self._v1(S, -1, up), self._v1(S, 1, down)
        return [x | y for x, y in zip(a, b)]

    def step(self, S, back=False):
        """one frame: a horizontal then a vertical move (or the other order), each stopped by
        tiles; back: the frame run backwards (up and down swap)"""
        a, b = self._v(self._h(S), back), self._h(self._v(S, back))
        return [x | y for x, y in zip(a, b)]

    def frames(self, x, y, n, back=False):
        out = [self.point(x, y)]
        for _ in range(n):
            out.append(self.step(out[-1], back))
        return out

    def flood(self, S, n):
        for _ in range(n):
            S = self.step(S)
        return S


def meets(*masks):
    return any(all(m[i] for m in masks) and _and(*(m[i] for m in masks)) for i in range(len(masks[0])))


def _and(*v):
    r = v[0]
    for x in v[1:]:
        r &= x
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--width", type=int, default=12)
    ap.add_argument("--rooms", help="comma-separated rooms (default: all 19)")
    ap.add_argument("--json")
    a = ap.parse_args()
    W = a.width
    result, total, flagged = {}, 0, 0
    for room in (a.rooms.split(",") if a.rooms else CH1_ORDER):
        r = parse(os.path.join(ROOT, "rooms", "vanilla", f"1a_{room}.txt"))
        zip_v = max((math.pi * math.hypot(tx - x, ty - y) / 60 for x, y, _, _, tx, ty in r.zipmovers), default=0)
        fall = 3 if r.fallblocks else 0
        VX = math.ceil(10 + 5 + zip_v) + 1                # 575 px/s, corner corrections
        VU = math.ceil(290 / 60 + 2 + zip_v) + 1          # super wall jump + lift, climb-up nudge
        VD = math.ceil(240 / 60 + 3 + fall + zip_v) + 1   # fast fall or dash, floor snap
        reg = Region(r, VX, VU, VD)
        pos = trace(room)
        n = len(read_tas(os.path.join(ROOT, "build", "chain_tas", room, "route.tas")))
        ks = []
        for k in range(0, n - W - 1):                     # hpc/make_tasks.py's windows
            F = reg.frames(*pos[k], W)
            B = reg.frames(*pos[k + W + 1], W + 1, back=True)
            hit = any(meets(F[t], B[W + 1 - t], reg.touch) for t in range(1, W + 1))
            for t in range(1, W + 1):                     # or touch, then leave the room
                if hit:
                    break
                T = [a & b for a, b in zip(F[t], reg.touch)]
                hit = any(T) and meets(reg.flood(T, W - t), reg.exit)
            if hit:
                ks.append(k)
        total += n - W - 1
        flagged += len(ks)
        result[room] = ks
        print(f"{room:8s} V={VX},{VU},{VD}  {len(ks):3d} of {n - W - 1:3d} windows  {ks}", flush=True)
    print(f"W={W}: {flagged} of {total} windows can reach an outside tile")
    if a.json:
        json.dump(result, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
