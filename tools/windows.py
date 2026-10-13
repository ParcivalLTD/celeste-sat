#!/usr/bin/env python3
"""
windows.py -- SAT on windows inside a known route: can any stretch of W
frames be done in fewer?

    tools/windows.py ROOM ROUTE.tas [--start ENTRY.h] [--width 8] [--jobs 2]

For every K (--from/--to limit the range), CBMC gets the route's exact state
after K frames and W free frames, and is asked whether she can reach the
route's state after K + W + 1 frames or the exit within them
(harness/window.c). The comparison (model/state_eq.h) leaves out the fields
that cannot change the rest of the route there, as found by replaying it
with them changed (sim/live.c; --exact compares every field). A yes is a
route one frame (or more) shorter: it is spliced in, replayed in the
simulator, and written out (if the replay is not faster, the window is asked
again with every field compared). A no proves that nothing gets from the
route's state at K to a state that agrees with its state at K + W + 1 on the
compared fields any faster; it does not rule out a faster route through the
window that ends in a different state (other subpixels, say).

Leaving the room also counts as reaching the target, so a window that ends
near the exit can find a faster *ending* that leaves in a different state.
That is a faster room, not a faster chapter: the next room's inputs may no
longer work (experiments/next_room.py checks). Each YES says which it is:
"[same exit state]" or "[different exit state]".

The windows stop short of the exit: the route's ending is what
tools/solve.py --from-frame checks.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat import cbmc  # noqa: E402
from celeste_sat.build import build, dump_state, replay, sh  # noqa: E402
from celeste_sat.paths import BUILD, ROOT, exe, read_text  # noqa: E402
from celeste_sat.tas import read_tas, write_tas  # noqa: E402


def dump(bdir, route, k, path, name):
    """the route's state after k frames as a C header defining `name`"""
    tmp = path + ".tmp"
    r = dump_state(bdir, route, k, tmp)
    if not os.path.exists(tmp):
        sys.exit(f"sim -s {k} failed: {r.stdout}{r.stderr}")
    text = open(tmp).read().replace("START_STATE", name).replace("START_FRAMES", name + "_FRAMES")
    os.remove(tmp)
    open(path, "w").write(text)


def exit_fields(path):
    """a state header without the lines that only say when it was taken"""
    return [l for l in read_text(path).splitlines() if not l.startswith("/*") and "START_FRAMES" not in l]


# the fields sim/live.c can find dead, in the order of the SF_* bits of model/state_eq.h
SF_NAMES = ("onGround wallSlideTimer stamina jumpGraceTimer varJump dashCooldown dashRefillCooldown dashAttack "
            "wallSpeedRetention forceMoveX wallBoost maxFall autoJump moveX facing hopWaitX dashDir").split()


def ignored(mask):
    return [n for i, n in enumerate(SF_NAMES) if mask >> i & 1]


def query(bdir, k, w, timeout, mask=0):
    """harness/window.c for the window after frame k -> (True, frames) / (False, None) /
    (None, None) on timeout, and seconds"""
    cmd = cbmc.command(f"{ROOT}/harness/window.c", "-I", bdir, "-I", f"{ROOT}/model", "-I", f"{ROOT}/harness",
                       f"-DW={w}", f'-DSTART_STATE_FILE="win_{k}_start.h"', f'-DTARGET_STATE_FILE="win_{k}_target.h"',
                       f"-DSF_IGNORE={mask}u")
    return cbmc.run(cmd, bdir, timeout, n=w)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("room")
    ap.add_argument("route")
    ap.add_argument("--start", help="state header the room starts from (default: its spawn)")
    ap.add_argument("--width", type=int, default=8, help="free frames per window (default 8)")
    ap.add_argument("--from", dest="k0", type=int, default=0, help="first K (default 0)")
    ap.add_argument("--to", dest="k1", type=int, help="last K (default: the last window before the exit)")
    ap.add_argument("--step", type=int, default=1, help="K increment (default 1)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--timeout", type=int, default=3600, help="seconds per query")
    ap.add_argument("--exact", action="store_true", help="compare every field (no liveness test)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    name = os.path.splitext(os.path.basename(a.room))[0]
    bdir = os.path.abspath(a.out or os.path.join(BUILD, f"windows_{name}"))
    build(a.room, bdir, a.start)
    flags = ['-DSTART_STATE_FILE="entry.h"'] if a.start else []
    r = sh(["gcc", "-O2", *flags, "-I", bdir, "-I", f"{ROOT}/model", "-o", exe(bdir, "live"), f"{ROOT}/sim/live.c"])
    if r.returncode:
        sys.exit(r.stderr)
    route = os.path.join(bdir, "route.tas")
    frames = read_tas(a.route)
    write_tas(route, frames, ["the known route"])
    n = replay(bdir, route)
    if not n:
        sys.exit(f"{a.route} does not leave {a.room}")
    frames = frames[:n]
    w = a.width
    k1 = min(a.k1 if a.k1 is not None else n, n - w - 2)
    ks = list(range(a.k0, k1 + 1, a.step))
    print(f"route leaves {name} on frame {n}; {len(ks)} windows of {w} free frames "
          f"(K = {ks[0]}..{ks[-1]}), {a.jobs} at a time", flush=True)
    masks = {}
    for k in ks:
        dump(bdir, route, k, f"{bdir}/win_{k}_start.h", "START_STATE")
        dump(bdir, route, k + w + 1, f"{bdir}/win_{k}_target.h", "TARGET_STATE")
        masks[k] = 0 if a.exact else int(sh([exe(bdir, "live"), str(k + w + 1), route]).stdout.strip())

    results = {}
    dump_state(bdir, route, n, os.path.join(bdir, "exit_route.h"))
    route_exit = exit_fields(os.path.join(bdir, "exit_route.h"))

    def splice(k, got, tag):
        """the shortest prefix of the counterexample that, spliced in, leaves the room sooner"""
        for j in range(1, w + 1):
            cand = frames[:k] + got[:j] + frames[k + w + 1:]
            p = os.path.join(bdir, f"win_{k}_better{tag}.tas")
            write_tas(p, cand, [f"{name}: frames {k + 1}..{k + w + 1} done in {j}"])
            e = replay(bdir, p)
            if e and e < n:
                dump_state(bdir, p, e, p + ".exit.h")
                return e, p, exit_fields(p + ".exit.h") == route_exit
        return None

    def run(k):
        mask = masks[k]
        found, got, dt = query(bdir, k, w, a.timeout, mask)
        best = splice(k, got, "") if found else None
        if found and not best and mask:                  # a left-out field mattered after all
            found, got, dt2 = query(bdir, k, w, a.timeout, 0)
            dt += dt2
            mask = 0
            best = splice(k, got, "_exact") if found else None
        line = f"  frames {k + 1:3d}..{k + w + 1:3d} in {w}: "
        if found is None:
            line += f"timeout ({dt:.0f}s)"
        elif not found:
            line += f"no ({dt:.0f}s)"
        else:
            line += (f"YES ({dt:.0f}s): leaves on frame {best[0]} instead of {n} "
                     f"[{'same' if best[2] else 'different'} exit state] -> {best[1]}" if best
                     else f"yes ({dt:.0f}s), but the spliced route does not replay faster (check)")
            if best:
                results.setdefault("better", []).append(dict(k=k, exit=best[0], route=best[1], same_exit=best[2]))
        results[k] = dict(found=found, seconds=round(dt), ignored=ignored(mask))
        print(line, flush=True)

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        list(ex.map(run, ks))
    json.dump({"room": a.room, "route": a.route, "exit": n, "width": w,
               "windows": {str(k): results[k] for k in ks}, "better": results.get("better", [])},
              open(os.path.join(bdir, "windows.json"), "w"), indent=1)
    no = sum(1 for k in ks if results[k]["found"] is False)
    to = sum(1 for k in ks if results[k]["found"] is None)
    print(f"{no} windows proven, {to} timed out, {len(results.get('better', []))} faster routes "
          f"(results in {bdir}/windows.json)")


if __name__ == "__main__":
    main()
