#!/usr/bin/env python3
"""
solve.py -- find the fastest way out of a room, and prove it when possible.

    tools/solve.py rooms/ledge.txt
    tools/solve.py rooms/ledge.txt --from-frame 9      # keep frames 1..9 of the
                                                       # best known run, optimise the rest
    tools/solve.py rooms/ledge.txt --tas my_route.tas  # start from your own route

Pipeline:
  1. build the model for this room (room.h + exact timer tables)
  2. beam search (fast, heuristic) -> an upper bound: a real route exiting on frame U;
     --polish restarts the beam from the middle of the best route to shorten the rest
  3. SAT descent: ask CBMC "can Madeline leave by frame U-1?"
       - counterexample  -> a faster route; replay it in the simulator, repeat
       - "no"            -> the current best is optimal (within the model; and,
                            with --from-frame K, given the first K frames)
       - timeout         -> report the best route and what is proven so far
  4. write best.tas (CelesteTAS format) and trace.json (for visualisation)
"""
import argparse, json, os, re, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, **kw)


def carries_lift(state_file):
    """does a state header have a lift speed in its grace time (Actor.LiftSpeed)?"""
    text = open(state_file).read()
    m = re.search(r"\.liftGraceTimer = (-?\d+)", text)
    return bool(m and int(m.group(1)) > 0)


def build(room_path, bdir, start=None):
    """room.h, timer tables, sim and beam for a room; `start` is an optional
    state header (START_STATE) to begin from instead of the spawn."""
    os.makedirs(bdir, exist_ok=True)
    r = sh([sys.executable, f"{ROOT}/tools/make_room.py", room_path, f"{bdir}/room.h"])
    if r.returncode: sys.exit(r.stderr)
    if start and carries_lift(start):
        with open(f"{bdir}/room.h", "a") as f:
            f.write("/* she enters with a lift speed still in its grace time */\n#define CARRIED_LIFT 1\n")
    gen = f"{bdir}/gen_tables"
    for cmd in (["gcc", "-O0", "-I", f"{ROOT}/model", "-o", gen, f"{ROOT}/tools/gen_tables.c"],):
        r = sh(cmd)
        if r.returncode: sys.exit(r.stderr)
    open(f"{bdir}/tables.h", "w").write(sh([gen]).stdout)
    flags = []
    if start:
        shutil.copy(start, f"{bdir}/entry.h")
        flags = ['-DSTART_STATE_FILE="entry.h"']
    for name, src, extra in (("sim", "sim/sim.c", []), ("beam", "search/beam.c", ["-fopenmp"])):
        r = sh(["gcc", "-O2", *extra, *flags, "-I", bdir, "-I", f"{ROOT}/model", "-o", f"{bdir}/{name}", f"{ROOT}/{src}"])
        if r.returncode: sys.exit(r.stderr)
    shutil.copy(f"{ROOT}/harness/solve.c", f"{bdir}/solve.c")
    shutil.copy(f"{ROOT}/harness/input_rules.h", f"{bdir}/input_rules.h")


REPRESS = 2   # jump/dash value: held, and pressed again with the other key (see model/celeste.h)


def _button(now, prev):
    """button value (0, 1 or REPRESS) from its two keys now and on the previous frame"""
    held, was = now[0] or now[1], prev[0] or prev[1]
    press = (now[0] and not prev[0]) or (now[1] and not prev[1])
    return 0 if not held else (REPRESS if was and press else 1)


NOTHING = (0, 0, 0, 0, False, 0)


def read_tas(path):
    """frames of (mx, my, jump, dash, grab, cdash) from a CelesteTAS-style
    file. J/K are the two jump keys, X/C the two dash keys and Z/V the two
    crouch dash keys: these buttons are 0 (released), 1 (held; a press after
    a release) or REPRESS (held and pressed again with the other key). G/H
    are grab."""
    frames, pj, pd, pz = [], (False, False), (False, False), (False, False)
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"): continue
        parts = [p.strip().upper() for p in line.split(",")]
        if not parts[0].isdigit(): continue
        n = int(parts[0])
        keys = set(parts[1:])
        unknown = keys - set("LRUDJKXCZVGH")
        if unknown:
            sys.exit(f"{path}: input {sorted(unknown)} is not modelled (line: {line})")
        j, d, z = ("J" in keys, "K" in keys), ("X" in keys, "C" in keys), ("Z" in keys, "V" in keys)
        mx = -1 if "L" in keys else 1 if "R" in keys else 0
        my = -1 if "U" in keys else 1 if "D" in keys else 0
        g = "G" in keys or "H" in keys
        for _ in range(n):
            frames.append((mx, my, _button(j, pj), _button(d, pd), g, _button(z, pz)))
            pj, pd, pz = j, d, z
    return frames


def tas_keys(frames):
    """the keys of each frame: a fresh press uses J (X), a press while the
    button is held switches to the other key"""
    out, jk, dk, zk = [], None, None, None

    def nxt(b, cur, keys):
        if not b: return None
        if cur is None: return keys[0]
        return (keys[1] if cur == keys[0] else keys[0]) if b == REPRESS else cur

    for mx, my, jmp, dash, grab, cdash in frames:
        jk, dk, zk = nxt(jmp, jk, "JK"), nxt(dash, dk, "XC"), nxt(cdash, zk, "ZV")
        k = []
        if mx < 0: k.append("L")
        if mx > 0: k.append("R")
        if my < 0: k.append("U")
        if my > 0: k.append("D")
        if jk: k.append(jk)
        if dk: k.append(dk)
        if zk: k.append(zk)
        if grab: k.append("G")
        out.append(tuple(k))
    return out


def write_tas(path, frames, header):
    out = [f"# {h}" for h in header]
    keys = tas_keys(frames)
    i = 0
    while i < len(keys):
        j = i
        while j < len(keys) and keys[j] == keys[i]: j += 1
        out.append(",".join([f"{j - i:4d}", *keys[i]]))
        i = j
    open(path, "w").write("\n".join(out) + "\n")


def replay(bdir, tas, json_out=None):
    cmd = [f"{bdir}/sim", tas] + (["-j", json_out] if json_out else [])
    r = sh(cmd)
    m = re.search(r"EXIT at frame (\d+)", r.stdout)
    return int(m.group(1)) if m else None


def cbmc(bdir, horizon, start_file, timeout):
    """True/False/None = found a route / proved impossible / timed out."""
    cmd = ["cbmc"] + (["--gcc"] if sys.platform == "win32" else []) + [
        "solve.c", "-I", ".", "-I", f"{ROOT}/model", f"-DNFRAMES={horizon}",
        "--trace", "--json-ui"]
    if start_file:
        cmd.append(f'-DSTART_STATE_FILE="{start_file}"')
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=bdir, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, None, time.time() - t0
    dt = time.time() - t0
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        sys.exit("could not parse CBMC output:\n" + r.stdout[-2000:] + r.stderr[-2000:])
    for msg in data:
        for res in msg.get("result", []):
            if res["status"] == "SUCCESS":
                return False, None, dt
            if res["status"] == "FAILURE":
                vals = {}
                for st in res.get("trace", []):
                    if st.get("stepType") != "assignment": continue
                    m = re.fullmatch(r"inputs\[(\d+)l?\]\.(mx|my|jump|dash|grab|cdash)", st.get("lhs", ""))
                    if m:
                        d = st["value"]["data"]
                        vals[(int(m.group(1)), m.group(2))] = (d == "TRUE") if d in ("TRUE", "FALSE") else int(d)
                frames = [(vals.get((i, "mx"), 0), vals.get((i, "my"), 0), vals.get((i, "jump"), 0),
                           vals.get((i, "dash"), 0), vals.get((i, "grab"), False), vals.get((i, "cdash"), 0))
                          for i in range(horizon)]
                return True, frames, dt
    sys.exit("unexpected CBMC output:\n" + r.stdout[-2000:] + r.stderr[-2000:])


def polish(bdir, inc, best, a):
    """Restart the beam search from the state after the first K frames of the
    best route, for K = best-15, best-25, ... A restart searches the rest of
    the route with a full beam; any shorter route replaces the best one and
    the schedule starts again."""
    improved = True
    while improved:
        improved = False
        for K in range(best - 15, 4, -10):
            write_tas(f"{bdir}/polish_in.tas", inc, ["polish input"])
            out = f"{bdir}/polish_out.tas"
            if os.path.exists(out):
                os.remove(out)
            t0 = time.time()
            sh([f"{bdir}/beam", "-k", str(a.beam_width), "-m", str(a.beam_cap), "-r", str(a.beam_rollout),
                "-x", str(a.exit_x), "-p", f"{bdir}/polish_in.tas", "-n", str(K), out])
            e = replay(bdir, out) if os.path.exists(out) else None
            print(f"polish: beam restarted after frame {K}: "
                  f"{e if e else 'no'} {'frames' if e else 'route'} ({time.time() - t0:.0f}s)", flush=True)
            if e is not None and e < best:
                inc, best = read_tas(out)[:e], e
                improved = True
                break
    return inc, best


def final_state(bdir, tas, frames):
    """the simulator's exact state after `frames` frames of `tas` (sim -s), as text"""
    out = f"{bdir}/tidy_state.h"
    sh([f"{bdir}/sim", "-s", str(frames), out, tas])
    return "".join(l for l in open(out) if not l.startswith("/*"))


def tidy(bdir, frames, best, keep, keep_exit=False):
    """Greedily replace inputs after frame `keep` with simpler ones whenever
    that does not make the run any slower: continue the previous input,
    nothing, or the same input with one button fewer. Frames up to `keep` are
    left alone, so a proof "given frames 1..keep" still refers to this route.
    Occasionally a simpler input is also faster; returns (inputs, frames).
    With keep_exit, a change is kept only if Madeline leaves the room on the
    same frame in exactly the same state (needed when the next room starts
    from that state)."""
    cur = list(frames)
    tmp = f"{bdir}/tidy.tas"
    if keep_exit:
        write_tas(tmp, cur, ["tidy"])
        target = final_state(bdir, tmp, best)
    i = keep
    while i < len(cur):
        mx, my, j, d, g, z = cur[i]
        # "continue the previous input" holds its buttons (a press again would
        # alternate the two keys, which is not simpler)
        prev = [tuple(min(v, 1) if k in (2, 3, 5) else v for k, v in enumerate(cur[i - 1]))] if i > 0 else []
        opts = prev + [NOTHING,
                (mx, 0, j, d, g, z), (mx, my, j, d, False, z), (0, my, j, d, g, z),
                (mx, my, 0, d, g, z), (mx, my, j, 0, g, z), (mx, my, j, d, g, 0),
                (mx, my, min(j, 1), min(d, 1), g, min(z, 1))]
        for o in opts:
            if o == cur[i]:
                continue
            trial = cur[:i] + [o] + cur[i + 1:]
            write_tas(tmp, trial, ["tidy"])
            e = replay(bdir, tmp)
            if keep_exit and (e != best or final_state(bdir, tmp, best) != target):
                continue
            if e is not None and e <= best:
                cur, best = trial[:e], e
                break
        i += 1
    return cur, best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("room")
    ap.add_argument("--tas", help="start from this route instead of running the beam search")
    ap.add_argument("--from-frame", type=int, default=0,
                    help="keep the first K frames of the best route fixed and optimise the rest")
    ap.add_argument("--beam-width", type=int, default=100000)
    ap.add_argument("--beam-cap", type=int, default=4,
                    help="beam: keep at most this many states per (position, state, dashes) cell (0 = no cap)")
    ap.add_argument("--beam-rollout", type=int, default=8, help="beam: frames of lookahead when ranking states")
    ap.add_argument("--exit-x", type=int, default=-1,
                    help="beam: only count leaving the room at this x (to line up with the next room's route)")
    ap.add_argument("--polish", action="store_true",
                    help="restart the beam from the state after the first K frames of the best route "
                         "(K = U-15, U-25, ...) until no restart finds a shorter route")
    ap.add_argument("--timeout", type=float, default=1800, help="seconds per SAT query")
    ap.add_argument("--out", help="output directory (default build/<room>)")
    ap.add_argument("--keep-exit", action="store_true",
                    help="tidy only where the exit state stays identical (for chaining rooms)")
    ap.add_argument("--start", help="state header to start from instead of the spawn "
                                    "(written by tools/chapter.py when entering from the previous room)")
    ap.add_argument("--no-sat", action="store_true",
                    help="skip the SAT descent (just replay, tidy and write outputs)")
    a = ap.parse_args()

    name = os.path.splitext(os.path.basename(a.room))[0]
    bdir = os.path.abspath(a.out or f"{ROOT}/build/{name}")
    build(a.room, bdir, a.start)

    # 1. upper bound
    if a.tas:
        inc = read_tas(a.tas)
        src = a.tas
    else:
        t0 = time.time()
        r = sh([f"{bdir}/beam", "-k", str(a.beam_width), "-m", str(a.beam_cap), "-r", str(a.beam_rollout),
                "-x", str(a.exit_x), f"{bdir}/beam.tas"])
        print(r.stdout.strip(), f"({time.time() - t0:.1f}s)")
        inc = read_tas(f"{bdir}/beam.tas")
        src = "beam search"
    write_tas(f"{bdir}/best.tas", inc, [f"from {src}"])
    best = replay(bdir, f"{bdir}/best.tas")
    if best is None: sys.exit("the starting route does not leave the room")
    inc = inc[:best]
    print(f"upper bound: {best} frames ({src})")

    if a.polish:
        inc, best = polish(bdir, inc, best, a)
        write_tas(f"{bdir}/best.tas", inc, [f"from {src}, polished"])

    # 2. fixed prefix
    K = a.from_frame
    start_file = "entry.h" if a.start else None
    if K:
        write_tas(f"{bdir}/prefix.tas", inc[:K], ["prefix"])
        sh([f"{bdir}/sim", "-s", str(K), f"{bdir}/start.h", f"{bdir}/prefix.tas"])
        start_file = "start.h"
        print(f"keeping frames 1..{K} fixed; the solver optimises frames {K + 1}..")

    # 3. SAT descent
    history = [dict(kind="beam" if not a.tas else "given", frames=best)]
    proven = False
    while not a.no_sat:
        target = best - 1
        horizon = target - K
        if horizon <= 0:
            proven = True
            break
        print(f"SAT: can she leave by frame {target}? ({horizon} free frames) ... ", end="", flush=True)
        found, frames, dt = cbmc(bdir, horizon, start_file, a.timeout)
        if found is None:
            print(f"timeout after {dt:.0f}s")
            history.append(dict(kind="timeout", frames=target, secs=round(dt)))
            break
        if not found:
            print(f"no -> {best} is optimal ({dt:.0f}s)")
            history.append(dict(kind="unsat", frames=target, secs=round(dt)))
            proven = True
            break
        cand = inc[:K] + frames
        write_tas(f"{bdir}/candidate.tas", cand, ["candidate"])
        e = replay(bdir, f"{bdir}/candidate.tas")
        if e is None or e > target:
            sys.exit(f"model mismatch: CBMC's route exits at {e} in the simulator (expected <= {target})")
        print(f"yes, found a {e}-frame route ({dt:.0f}s)")
        history.append(dict(kind="sat", frames=e, secs=round(dt)))
        best, inc = e, cand[:e]
        write_tas(f"{bdir}/best.tas", inc, [f"improved by SAT: {e} frames"])

    # 4. tidy: simplify inputs frame by frame (easier to read, sometimes faster)
    inc, tidied = tidy(bdir, inc, best, K, a.keep_exit)
    if tidied < best:
        if proven:
            print(f"WARNING: tidy found a {tidied}-frame route after the SAT proof said {best - 1} is impossible "
                  f"-- the model and the proof disagree")
        else:
            print(f"tidy: simpler inputs are also faster: {tidied} frames")
            history.append(dict(kind="tidy", frames=tidied))
        best = tidied

    # 5. outputs
    note = (f"optimal: no route leaves by frame {best - 1}" if proven else
            "no SAT run" if a.no_sat else "best found (not proven optimal)")
    if K: note += f" -- given frames 1..{K}"
    write_tas(f"{bdir}/best.tas", inc, [f"room {name}: exits on frame {best}", note])
    replay(bdir, f"{bdir}/best.tas", f"{bdir}/trace.json")
    json.dump(dict(room=name, frames=best, proven=proven, from_frame=K, history=history),
              open(f"{bdir}/result.json", "w"), indent=1)
    print(f"\n{note}\nroute: {bdir}/best.tas")
    print(open(f"{bdir}/best.tas").read())


if __name__ == "__main__":
    main()
