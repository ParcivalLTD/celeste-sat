#!/usr/bin/env python3
"""
edge_windows.py -- which window proofs of the Chapter 1 certificate can the
tiles outside the rooms (`; outside`) change?

    python3 experiments/edge_windows.py [--width 12] [--rooms lvl_1,...] [--exact 4] [--json out.json]

The Leonardo windows (commit 9e3dd4f) were proven with everything outside a
room's grid as air. For Chapter 1 the outside tiles are the only model change
since then (the dream-block, chaser and touch-switch changes compile out), so
a window's "no" can only change if some input sequence in it makes a tile
check answer differently: a box with no solid room tile that covers a solid
outside tile, or one of slip_check's points on a solid outside tile. Until
the first such check a run is the old model's. A window is cleared if no such
check is reachable in its W free frames, on the way to the route's state after
K + W + 1 frames or on the way out through the goal exit (leaving the room
also ends a window; a "; leave" is a failure, like dying).

Two stages, both sound (they can only over-approximate where she can be):

1. --exact T: experiments/edge_reach.c steps the model with and without the
   outside tiles side by side on every input sequence of the first T frames
   (duplicate states merged). It reports where the two part ways, if they do,
   else her positions and the largest speeds (and lift) the states carry
   after T frames. T = 0 gives the start state's speeds (stage 2 needs them).

2. A flood of the old model's free space for the remaining frames: positions
   as one bitmask per row, tiles blocking, entity solids left out, the ducking
   box. Per frame a horizontal, vertical, horizontal, vertical sweep (or
   starting vertically: corner and dash corrections turn a move's corner), each
   of up to VX / VU / VD px (bounds() below). Everything a frame passes counts
   as a place a check can happen, past the room bounds too (the model clamps
   her only at the end of the frame); the next frame starts from the clamped
   positions. The backward flood from the window's end state runs the same
   frames in reverse. A window is flagged if, at a free frame t, a position
   reachable forwards and backwards has a differing probe (her box, height 6,
   11 or 17, at dx in [-5, 5], dy in [-6, 4]; slip_check's points), or a
   differing position floods on to the goal exit in the frames left.

Unflagged windows keep their Leonardo proof; flagged ones need
tools/windows.py again.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from celeste_sat import room_header  # noqa: E402
from celeste_sat.build import carries_lift  # noqa: E402
from celeste_sat.community import CH1_ORDER  # noqa: E402
from celeste_sat.room import parse  # noqa: E402
from celeste_sat.tas import read_tas  # noqa: E402

PX, PY0, PY1 = 5, -6, 4   # probe offsets: wall bounce 5, corner corrections, climb hop 6 up, ledge 4 down
M = 8                     # how far a check reaches past her box, for the exit mask


def trace(room):
    bdir = os.path.join(ROOT, "build", "chain_tas", room)
    out = os.path.join(bdir, "edge_trace.json")
    subprocess.run([os.path.join(bdir, "sim"), "-j", out, "route.tas"], cwd=bdir,
                   check=True, capture_output=True)
    return [(f["x"], f["y"]) for f in json.load(open(out))["frames"]]


def floor8(v):
    return v // 8


def bounds(zip_peak, falling, vx0=0.0, vy0=0.0, lx0=0.0, ly0=0.0):
    """(VX, VU, VD, push): px per frame of move_h, of move_v up and down, and of a moving solid's
    push. Speeds: harness/input_rules.h's bounds (400 and 250 px/s, checked by tests/fuzz.c,
    assumed by every window proof) or, with a lift boost (Actor.LiftSpeed: at most the speed of
    the solid that gave it, capped at 250 sideways and 130 up; falling blocks only move down and
    give none), a duck hyper with the lift, (260 + Lx) * 1.25, and a super wall jump with it,
    160 + Ly; raised to what the start states carry; +0.5 for the subpixel remainder. Pushes: the
    fastest zip mover (zip_peak px/s), a falling block (160 px/s, down)."""
    lx, ly = max(min(250.0, zip_peak), lx0), max(min(130.0, zip_peak), ly0)
    sx = max(400.0, (260 + lx) * 1.25 if lx else 0, vx0)
    sy = max(250.0, 160 + ly, vy0)
    VX = math.ceil(sx / 60 + 0.5)                   # MoveH(Speed.X * dt) with the remainder (|r| <= 0.5)
    VY = math.ceil(sy / 60 + 0.5)
    push = math.ceil(max(zip_peak, 160 if falling else 0) / 60)
    return VX, VY, VY, push


class Region:
    """her feet positions (x, y) in and around a room, one bitmask per row (bit x - X0)"""

    def __init__(self, r, VX, VU, VD, push):
        self.pw, self.ph = pw, ph = len(r.rows[0]) * 8, len(r.rows) * 8
        self.VX, self.VU, self.VD, self.push = VX, VU, VD, push
        # where a frame can take her: past the side bounds by a move, above the top clamp
        # (Top = -24) and below the death line (Top > ph + 4) by one frame's move
        self.XL, self.XR = 4 - VX - 5 - 2 * push - 1, pw - 4 + VX + 5 + 2 * push + 1
        self.YT, self.YB = -18 - VU - 4 - 2 * push - 2, ph + 15 + VD + 4 + 2 * push + 3
        self.X0, self.Y0 = self.XL - 1, self.YT - 1
        nrows = self.YB + 2 - self.Y0
        solid = lambda cx, cy: 0 <= cy < len(r.rows) and 0 <= cx < len(r.rows[0]) and r.rows[cy][cx] == "#"
        out = r.outside
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
            if 4 + PX + 4 <= x <= pw - 4 - PX - 4 and 17 + 6 + 2 < y < ph - 4 - 1:
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
                        if (floor8(px), floor8(py)) in out:
                            return True
            return False

        # the goal exits: side and span along the edge, widened by a tile
        goals = [(e[0], e[1] - 8, e[2] + 8) for e in r.exits if e[3]] or [("right", -math.inf, math.inf)]
        self.free, self.touch, self.exit = [0] * nrows, [0] * nrows, [0] * nrows
        for i in range(nrows):
            y = i + self.Y0
            f = t = e = 0
            for x in range(self.XL, self.XR + 1):
                b = 1 << (x - self.X0)
                if not (self.YT <= y <= self.YB):
                    continue
                if not any(solid(cx, cy) for cx in (floor8(x - 4), floor8(x + 3))
                           for cy in (floor8(y - 6), floor8(y - 1))):
                    f |= b
                    if differs(x, y):
                        t |= b
                for side, lo, hi in goals:
                    along = x if side in ("up", "down") else y - 6
                    if lo <= along <= hi and ((side == "left" and x - 4 - M < 0) or (side == "right" and x + 4 + M > pw)
                                              or (side == "up" and y - 11 - M < 0) or (side == "down" and y + M > ph)):
                        e |= b
            self.free[i], self.touch[i], self.exit[i] = f, t, e
        # where a moving solid can push or carry her: her box within push + 2 px of the area it
        # sweeps (a zip mover between its two ends, a falling block down to the bottom)
        swept = [(min(x, tx), min(y, ty), max(x, tx) + w, max(y, ty) + h) for x, y, w, h, tx, ty in r.zipmovers]
        swept += [(x, y, x + w, ph + 32) for x, y, w, h, _ in r.fallblocks]
        g = push + 2
        self.pushable = [0] * nrows
        for i in range(nrows):
            y = i + self.Y0
            m = 0
            for x0, y0, x1, y1 in swept:
                if y - 11 - g < y1 and y + g > y0:
                    lo, hi = max(self.XL, x0 - 4 - g + 1), min(self.XR, x1 + 4 + g - 1)
                    for x in range(lo, hi + 1):
                        m |= 1 << (x - self.X0)
            self.pushable[i] = m & self.free[i]
        self.r_m13, self.r_m18 = -13 - self.Y0, -18 - self.Y0
        self.r_dead = ph + 15 - self.Y0                  # rows below: dead at the end of the frame
        self.b4, self.bR = 4 - self.X0, pw - 4 - self.X0
        self.inb = ((1 << (self.bR + 1)) - 1) & ~((1 << self.b4) - 1)    # 4 <= x <= pw - 4

    def point(self, x, y):
        S = [0] * len(self.free)
        S[y - self.Y0] = 1 << (x - self.X0)
        return S

    # ---- moves within a frame ----
    def _hstep(self, S):
        return [s | ((s << 1 | s >> 1) & f) for s, f in zip(S, self.free)]

    def _vstep(self, S, d):
        """one px in direction d (-1 up, +1 down), stopped by tiles"""
        m = len(S)
        return [S[i] | ((S[i - d] if 0 <= i - d < m else 0) & self.free[i]) for i in range(m)]

    def _h(self, S, n):
        for _ in range(n):
            S = self._hstep(S)
        return S

    def _v(self, S, up, down):
        a, b = S, S
        for _ in range(up):
            a = self._vstep(a, -1)
        for _ in range(down):
            b = self._vstep(b, 1)
        return [x | y for x, y in zip(a, b)]

    @staticmethod
    def _or(*sets):
        return [_or_all(row) for row in zip(*sets)]

    def frame(self, S, back=False):
        """everything one frame can pass (Player.Update, then the moving solids), as one of
        (1) nudges before the move (climb-up 2 up, dash floor snap 3 down), move_h, move_v with at
            most one upward corner correction (up to 5 px sideways, OnCollideV);
        (2) Speed.Y = 0: the floor snap, move_h with at most one dash corner correction (4 px up or
            down, OnCollideH, which needs Speed.Y == 0), no vertical move;
        with a moving solid's push before and after (only where one can reach her). Backwards: the same steps in reverse order,
        up and down swapped."""
        up, down = (self.VD, self.VU) if back else (self.VU, self.VD)
        p = self.push

        def push(S):
            if not p:
                return S
            P = [a & b for a, b in zip(S, self.pushable)]
            if not any(P):
                return S
            return self._or(S, self._h(self._v(P, p, p), p))

        def pre(S):
            return self._v(S, 3 if back else 2, 2 if back else 3)

        def snap(S):
            return self._v(S, 3, 0) if back else self._v(S, 0, 3)

        def h_plain(S):
            return self._h(S, self.VX)

        def h_corner(S):                               # h^a, at most one v-nudge of <= 4, h^b; a + b <= VX
            A, C = S, self._v(S, 4, 4)
            for _ in range(self.VX):
                A = self._hstep(A)
                C = self._or(self._hstep(C), self._v(A, 4, 4))
            return self._or(A, C)

        def v_corner(S):                               # v^a, at most one h-nudge of <= 5, v^b
            out = []
            for d, n in ((-1, up), (1, down)):
                a, c = S, self._h(S, 5)
                for _ in range(n):
                    a = self._vstep(a, d)
                    c = self._or(self._vstep(c, d), self._h(a, 5))
                out += [a, c]
            return self._or(*out)

        cases = ((push, pre, h_plain, v_corner, push), (push, snap, h_corner, push))
        res = []
        for steps in cases:
            T = S
            for f in (reversed(steps) if back else steps):
                T = f(T)
            res.append(T)
        return self._or(*res)

    # ---- the end of a frame (Level.EnforceBounds, falling out) ----
    def clamp(self, S):
        """where a frame that passed S can end"""
        S = list(S)
        for i, s in enumerate(S):
            if s & ~self.inb:
                if s & ((1 << self.b4) - 1):
                    s |= 1 << self.b4                    # player.Left = bounds.Left
                if s >> (self.bR + 1):
                    s |= 1 << self.bR
                S[i] = s & self.inb & self.free[i]
        for i in range(self.r_m13):                      # Top < -24: Top = -24 (standing -13, ducking -18)
            if S[i]:
                S[self.r_m13] |= S[i] & self.free[self.r_m13]
                if i < self.r_m18:
                    S[self.r_m18] |= S[i] & self.free[self.r_m18]
                    S[i] = 0
        for i in range(self.r_dead + 1, len(S)):
            S[i] = 0
        return S

    def unclamp(self, S):
        """where a frame that ends in S can have passed last (the inverse of clamp)"""
        S = list(S)
        low, high = (1 << self.b4) - 1, ~((1 << (self.bR + 1)) - 1)
        for i, s in enumerate(S):
            if s >> self.b4 & 1:
                s |= low
            if s >> self.bR & 1:
                s |= high
            S[i] = s & self.free[i]
        for i in range(self.r_m13):
            S[i] |= (S[self.r_m13] | (S[self.r_m18] if i < self.r_m18 else 0)) & self.free[i]
        return S

    def frames(self, S, n, back=False):
        """out[t]: everything frame t can pass (t = 1..n), out[0] = S. Forwards from frame-end
        positions S; backwards from S at the end of the last frame"""
        out, E = [S], S
        for _ in range(n):
            V = self.frame(self.unclamp(E) if back else E, back)
            out.append(V)
            E = [v & self.inb for v in V] if back else self.clamp(V)
        return out


def _or_all(row):
    v = 0
    for x in row:
        v |= x
    return v


def meets(*masks):
    for row in zip(*masks):
        v = row[0]
        for m in row[1:]:
            v &= m
        if v:
            return True
    return False


def flagged_from(reg, F, B, W, t0):
    """a differing check reachable at a free frame t >= t0 on the way to the window's end
    state, or on the way out of the room through the goal exit"""
    if any(meets(F[t], B[W + 1 - t], reg.touch) for t in range(t0, W + 1)):
        return True
    for t in range(t0, W + 1):
        X = [a & b for a, b in zip(F[t], reg.touch)]
        if any(X):
            for _ in range(W - t + 1):                   # the rest of frame t, then the frames left
                X = reg.frame(X)
            if meets(X, reg.exit):
                return True
    return False


def build_reach(room):
    """experiments/edge_reach.c linked with two solver builds of the room's model: as it is now
    (new_) and without its "; outside" lines (old_, everything outside air as at 9e3dd4f)"""
    bdir = os.path.join(ROOT, "build", "chain_tas", room)
    out = os.path.join(ROOT, "build", "edge_reach", room)
    os.makedirs(out, exist_ok=True)
    src = os.path.join(ROOT, "rooms", "vanilla", f"1a_{room}.txt")
    lines = open(src).read().splitlines(keepends=True)
    old_txt = os.path.join(out, "room_old.txt")
    open(old_txt, "w").write("".join(l for l in lines if not l.startswith("; outside ")))
    room_header.write(src, os.path.join(out, "room_new.h"))
    room_header.write(old_txt, os.path.join(out, "room_old.h"))
    for name in ("new", "old"):
        open(os.path.join(out, f"model_{name}.c"), "w").write(
            f"/* written by experiments/edge_windows.py */\n#include <assert.h>\n#define MODEL_ASSUME(c) assert(c)\n"
            f'#define ROOM_HEADER "room_{name}.h"\n#define MODEL_PREFIX {name}\n#include "celeste.c"\n')
    flags = []
    if os.path.exists(os.path.join(bdir, "entry.h")):
        shutil.copy(os.path.join(bdir, "entry.h"), os.path.join(out, "entry.h"))
        flags = ['-DSTART_STATE_FILE="entry.h"']
        if carries_lift(os.path.join(bdir, "entry.h")):
            for name in ("new", "old"):
                with open(os.path.join(out, f"room_{name}.h"), "a") as f:
                    f.write("#define CARRIED_LIFT 1\n")
    binary = os.path.join(out, "edge_reach")
    subprocess.run(["gcc", "-O2", *flags, "-I", out, "-I", bdir, "-I", os.path.join(ROOT, "model"),
                    "-I", os.path.join(ROOT, "sim"), "-o", binary, os.path.join(ROOT, "experiments", "edge_reach.c"),
                    os.path.join(out, "model_new.c"), os.path.join(out, "model_old.c")], check=True)
    return binary


def exact_prefix(room, T, ks, jobs):
    """edge_reach's answer for each K: the first T frames of every input sequence, run exactly"""
    binary = build_reach(room)
    route = os.path.join(ROOT, "build", "chain_tas", room, "route.tas")

    def one(k):
        r = subprocess.run([binary, route, str(T), str(k), str(k)], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"{room} K {k}: {r.stderr}")
        return k, r.stdout.split()

    with ThreadPoolExecutor(jobs) as ex:
        return dict(ex.map(one, ks))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--width", type=int, default=12)
    ap.add_argument("--rooms", help="comma-separated rooms (default: all 19)")
    ap.add_argument("--exact", type=int, default=0, metavar="T",
                    help="run the model exhaustively for the first T frames of the windows the flood "
                         "alone flags (experiments/edge_reach.c), then flood the rest")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--json")
    a = ap.parse_args()
    W = a.width
    result, total, flagged = {}, 0, 0
    for room in (a.rooms.split(",") if a.rooms else CH1_ORDER):
        r = parse(os.path.join(ROOT, "rooms", "vanilla", f"1a_{room}.txt"))
        zip_peak = max((math.pi * math.hypot(tx - x, ty - y) for x, y, _, _, tx, ty in r.zipmovers), default=0)
        regions = {}
        pos = trace(room)

        def check(k, line, t0):
            """line: edge_reach's output for K after t0 exact frames"""
            if line[1] == "yes":
                return True
            vi, li = line.index("vmax"), line.index("lift")
            vb = bounds(zip_peak, bool(r.fallblocks), *map(float, (line[vi + 1], line[vi + 2], line[li + 1], line[li + 2])))
            if vb not in regions:
                regions[vb] = Region(r, *vb)
            reg = regions[vb]
            S = [0] * len(reg.free)
            for xy in line[line.index("pos") + 1:]:
                x, y = map(int, xy.split(","))
                S[y - reg.Y0] |= 1 << (x - reg.X0)
            F = [None] * t0 + reg.frames(S, W - t0)
            B = reg.frames(reg.point(*pos[k + W + 1]), W, back=True)
            return flagged_from(reg, F, B, W, t0 + 1)

        n = len(read_tas(os.path.join(ROOT, "build", "chain_tas", room, "route.tas")))
        allk = list(range(0, n - W - 1))                  # hpc/make_tasks.py's windows
        ks = [k for k, line in sorted(exact_prefix(room, 0, allk, a.jobs).items()) if check(k, line, 0)]
        flood_only = len(ks)
        if a.exact and ks:
            ks = [k for k, line in sorted(exact_prefix(room, a.exact, ks, a.jobs).items()) if check(k, line, a.exact)]
        total += len(allk)
        flagged += len(ks)
        result[room] = ks
        print(f"{room:8s} {len(ks):3d} of {len(allk):3d} windows (flood alone: {flood_only})  {ks}", flush=True)
    print(f"W={W}: {flagged} of {total} windows can reach a check the outside tiles decide")
    if a.json:
        json.dump(result, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
