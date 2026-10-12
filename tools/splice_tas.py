#!/usr/bin/env python3
"""
splice_tas.py -- turn faster windows into a route, and a route into a TAS to
play in the game.

1. Combine the faster windows tools/windows.py found in one room:

       python3 tools/splice_tas.py combine rooms/vanilla/1a_lvl_6a.txt build/chain_tas/lvl_6a/route.tas \\
           results/leonardo/cert/w12/lvl_6a_k0-31/windows.json results/leonardo/cert/w16/lvl_6a_*/windows.json \\
           --start build/chain_tas/entry_lvl_6a.h -o build/splice/lvl_6a.tas

   Every "better" entry of the windows.json files is one window [k, k+W+1)
   of the route done in fewer frames, reaching the route's own state. Windows
   that do not overlap can be applied together; this picks the best set of
   non-overlapping ones (most frames saved), applies them, replays the result
   and checks that it leaves the room in exactly the state the original route
   leaves it in (so the next room's inputs still work). If the combination
   does not replay as expected, it falls back to applying them one at a time,
   keeping each one that still checks out.

2. Put rooms into the community TAS:

       python3 tools/splice_tas.py chapter --room lvl_6a=build/splice/lvl_6a.tas \\
           --room lvl_12=build/splice/lvl_12.tas -o build/splice/1A_candidate.tas

   writes the community 1A.tas (celeste_sat/community.py) with those rooms'
   inputs replaced and everything else -- the level start, the 40-frame
   waits of the transitions, the other rooms -- as it was. Check it in the
   model with `python3 tests/chain_tas.py --tas build/splice/1A_candidate.tas`
   (every room must still leave on its last frame), then play it in Celeste
   Studio: CelesteTAS writes the new ChapterTime at the end.
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat import community  # noqa: E402
from celeste_sat.build import build, dump_state, replay  # noqa: E402
from celeste_sat.paths import BUILD, read_text, write_text  # noqa: E402
from celeste_sat.tas import read_tas, tas_lines, write_tas  # noqa: E402


# ---- combining windows -----------------------------------------------------

def state_fields(path):
    """a state header without the lines that only say when it was taken"""
    return [l for l in read_text(path).splitlines() if not l.startswith("/*") and "START_FRAMES" not in l]


def window_segment(orig, k, w, better):
    """the inputs a faster window puts in place of orig[k:k+w+1] (better = orig[:k] + mid + orig[k+w+1:])"""
    tail = len(orig) - (k + w + 1)
    mid = better[k:len(better) - tail]
    if better[:k] != orig[:k] or better[len(better) - tail:] != orig[k + w + 1:] or len(mid) > w:
        raise ValueError(f"window at k={k}, W={w} is not a splice of the original route")
    return mid


def apply_windows(orig, wins):
    """orig with every window (k, w, mid) replaced by mid; the windows must not overlap"""
    out = list(orig)
    for k, w, mid in sorted(wins, key=lambda x: -x[0]):        # from the end, so earlier indices stay put
        out[k:k + w + 1] = mid
    return out


def best_disjoint(wins):
    """the non-overlapping subset of windows (k, w, mid) that saves the most frames (weighted interval scheduling)"""
    wins = sorted(wins, key=lambda x: x[0] + x[1] + 1)          # by end
    ends = [k + w + 1 for k, w, _ in wins]
    best = [(0, [])]                                            # best[i]: using the first i windows
    for i, (k, w, mid) in enumerate(wins):
        j = max((p + 1 for p in range(i) if ends[p] <= k), default=0)
        take = (best[j][0] + (w + 1 - len(mid)), best[j][1] + [wins[i]])
        best.append(max(best[i], take, key=lambda t: t[0]))
    return best[-1][1]


def read_windows(paths, orig):
    """every faster window in these windows.json files -> [(k, w, mid)]"""
    wins = []
    for pattern in paths:
        for path in sorted(glob.glob(pattern)) or [pattern]:
            d = json.loads(read_text(path))
            for b in d.get("better", []):
                route = b["route"]
                if not os.path.exists(route):             # written on another machine: look next to the json
                    route = os.path.join(os.path.dirname(path), os.path.basename(route))
                wins.append((b["k"], d["width"], window_segment(orig, b["k"], d["width"], read_tas(route))))
    return wins


def combine(a):
    bdir = os.path.join(BUILD, "splice", os.path.splitext(os.path.basename(a.room))[0])
    build(a.room, bdir, a.start)
    orig_path = os.path.join(bdir, "original.tas")
    orig = read_tas(a.route)
    write_tas(orig_path, orig, ["the original route"])
    n = replay(bdir, orig_path)
    if not n:
        sys.exit(f"{a.route} does not leave {a.room}")
    orig = orig[:n]
    dump_state(bdir, orig_path, n, os.path.join(bdir, "exit_original.h"))
    target = state_fields(os.path.join(bdir, "exit_original.h"))

    def check(frames, tag):
        """leaves on frame len(frames), in the original exit state?"""
        p = os.path.join(bdir, f"{tag}.tas")
        write_tas(p, frames, [tag])
        e = replay(bdir, p)
        if e != len(frames):
            return False
        dump_state(bdir, p, e, os.path.join(bdir, f"exit_{tag}.h"))
        return state_fields(os.path.join(bdir, f"exit_{tag}.h")) == target

    wins = read_windows(a.windows, orig)
    print(f"{a.route}: leaves on frame {n}; {len(wins)} faster windows")
    chosen = best_disjoint(wins)
    frames = apply_windows(orig, chosen)
    if chosen and not check(frames, "combined"):
        print("  the best set does not replay to the same exit together; adding windows one at a time")
        chosen, frames = [], orig
        for win in sorted(wins, key=lambda x: len(x[2]) - x[1]):     # most frames saved first
            if any(not (win[0] + win[1] + 1 <= k or k + w + 1 <= win[0]) for k, w, _ in chosen):
                continue
            trial = apply_windows(orig, chosen + [win])
            if check(trial, "trial"):
                chosen, frames = chosen + [win], trial
    for k, w, mid in sorted(chosen):
        print(f"  frames {k + 1}..{k + w + 1} in {len(mid)}: -{w + 1 - len(mid)}")
    write_tas(a.out, frames, [f"{os.path.basename(a.route)} with {len(chosen)} faster windows: "
                              f"{len(frames)} frames instead of {n}, same exit state"])
    print(f"{len(frames)} frames instead of {n} (-{n - len(frames)}), same exit state -> {a.out}")


# ---- the community TAS with rooms replaced -----------------------------------

def replace_rooms(text, routes):
    """the CelesteTAS file `text` with the input lines of each #room in `routes` ({room: frames})
    replaced; what comes before a room's first input and its trailing bare frame counts
    (the transition's wait) stay. The ChapterTime line is dropped (CelesteTAS rewrites it)."""
    lines = [l for l in text.splitlines() if not l.startswith("ChapterTime:")]
    out, i, done = [], 0, set()
    while i < len(lines):
        s = lines[i].strip()
        room = s[1:] if s.startswith("#") and len(s) > 1 and not s[1].isspace() else None
        out.append(lines[i])
        i += 1
        if room not in routes:
            continue
        j = i                                          # the room's lines run to the next label or the end
        while j < len(lines) and not (lines[j].strip().startswith("#") and len(lines[j].strip()) > 1
                                      and not lines[j].strip()[1].isspace()):
            j += 1
        body = lines[i:j]
        inputs = [n for n, l in enumerate(body) if l.strip()[:1].isdigit()]
        if not inputs:
            sys.exit(f"#{room} has no input lines")
        last = len(inputs)                             # trailing bare counts: the transition's wait
        while last > 0 and body[inputs[last - 1]].strip().isdigit():
            last -= 1
        first, end = inputs[0], inputs[last - 1] + 1
        out += body[:first] + [l.rstrip() for l in tas_lines(routes[room])] + body[end:]
        done.add(room)
        i = j
    missing = set(routes) - done
    if missing:
        sys.exit(f"not in the TAS: {', '.join(sorted(missing))}")
    return "\n".join(out) + "\n"


def chapter(a):
    routes = {}
    for spec in a.room:
        room, path = spec.split("=", 1)
        routes[room.lstrip("#")] = read_tas(path)
    write_text(a.out, replace_rooms(community.fetch("1A.tas", a.tas), routes))
    print(f"wrote {a.out} ({', '.join(f'{r}: {len(f)} frames' for r, f in routes.items())})\n"
          f"check it in the model:  python3 tests/chain_tas.py --tas {a.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("combine", help="combine faster windows of one room")
    c.add_argument("room")
    c.add_argument("route", help="the route the windows were computed on")
    c.add_argument("windows", nargs="+", help="windows.json files (globs allowed)")
    c.add_argument("--start", help="state header the room starts from (as for tools/windows.py)")
    c.add_argument("-o", "--out", required=True)
    h = sub.add_parser("chapter", help="the community TAS with some rooms replaced")
    h.add_argument("--room", action="append", required=True, metavar="ROOM=ROUTE.tas")
    h.add_argument("--tas", help="the TAS to start from (default: the community 1A.tas)")
    h.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    {"combine": combine, "chapter": chapter}[a.cmd](a)


if __name__ == "__main__":
    main()
