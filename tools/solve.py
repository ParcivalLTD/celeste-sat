#!/usr/bin/env python3
"""
solve.py -- find the fastest way out of a room, and prove it when possible.

    tools/solve.py rooms/ledge.txt
    tools/solve.py rooms/ledge.txt --from-frame 9      # keep frames 1..9 of the
                                                       # best known run, optimise the rest
    tools/solve.py rooms/ledge.txt --tas my_route.tas  # start from your own route

Pipeline:
  1. build the model for this room (room.h + exact timer tables)
  2. beam search (fast, heuristic) -> an upper bound: a real route exiting on frame U
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


def build(room_path, bdir):
    os.makedirs(bdir, exist_ok=True)
    r = sh([sys.executable, f"{ROOT}/tools/make_room.py", room_path, f"{bdir}/room.h"])
    if r.returncode: sys.exit(r.stderr)
    gen = f"{bdir}/gen_tables"
    for cmd in (["gcc", "-O0", "-I", f"{ROOT}/model", "-o", gen, f"{ROOT}/tools/gen_tables.c"],):
        r = sh(cmd)
        if r.returncode: sys.exit(r.stderr)
    open(f"{bdir}/tables.h", "w").write(sh([gen]).stdout)
    for name, src in (("sim", "sim/sim.c"), ("beam", "search/beam.c")):
        r = sh(["gcc", "-O2", "-I", bdir, "-I", f"{ROOT}/model", "-o", f"{bdir}/{name}", f"{ROOT}/{src}"])
        if r.returncode: sys.exit(r.stderr)
    shutil.copy(f"{ROOT}/harness/solve.c", f"{bdir}/solve.c")


def read_tas(path):
    frames = []
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"): continue
        parts = [p.strip().upper() for p in line.split(",")]
        n = int(parts[0])
        inp = (-1 if "L" in parts else 1 if "R" in parts else 0,
               -1 if "U" in parts else 1 if "D" in parts else 0,
               "J" in parts or "K" in parts, "X" in parts or "C" in parts)
        frames += [inp] * n
    return frames


def write_tas(path, frames, header):
    out = [f"# {h}" for h in header]
    i = 0
    while i < len(frames):
        j = i
        while j < len(frames) and frames[j] == frames[i]: j += 1
        mx, my, jmp, dash = frames[i]
        toks = [f"{j - i:4d}"]
        if mx < 0: toks.append("L")
        if mx > 0: toks.append("R")
        if my < 0: toks.append("U")
        if my > 0: toks.append("D")
        if jmp: toks.append("J")
        if dash: toks.append("X")
        out.append(",".join(toks))
        i = j
    open(path, "w").write("\n".join(out) + "\n")


def replay(bdir, tas, json_out=None):
    cmd = [f"{bdir}/sim", tas] + (["-j", json_out] if json_out else [])
    r = sh(cmd)
    m = re.search(r"EXIT at frame (\d+)", r.stdout)
    return int(m.group(1)) if m else None


def cbmc(bdir, horizon, start_file, timeout):
    """True/False/None = found a route / proved impossible / timed out."""
    cmd = ["cbmc", "solve.c", "-I", ".", "-I", f"{ROOT}/model", f"-DNFRAMES={horizon}",
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
                    m = re.fullmatch(r"inputs\[(\d+)l?\]\.(mx|my|jump|dash)", st.get("lhs", ""))
                    if m:
                        d = st["value"]["data"]
                        vals[(int(m.group(1)), m.group(2))] = (d == "TRUE") if d in ("TRUE", "FALSE") else int(d)
                frames = [(vals.get((i, "mx"), 0), vals.get((i, "my"), 0),
                           vals.get((i, "jump"), False), vals.get((i, "dash"), False)) for i in range(horizon)]
                return True, frames, dt
    sys.exit("unexpected CBMC output:\n" + r.stdout[-2000:] + r.stderr[-2000:])


def tidy(bdir, frames, best, keep):
    """Greedily replace inputs after frame `keep` with simpler ones (continue the
    previous input, hold right, or nothing) whenever that does not make the
    run any slower. Purely cosmetic: the result exits on the same frame."""
    cur = list(frames)
    tmp = f"{bdir}/tidy.tas"
    for i in range(keep, len(cur)):
        mx, my, j, d = cur[i]
        opts = [(mx, 0, j, d)] if my != 0 else []          # drop an up/down that does nothing
        opts += ([cur[i - 1]] if i > 0 else []) + [(1, 0, False, False), (0, 0, False, False)]
        for o in opts:
            if o == cur[i]:
                break
            trial = cur[:i] + [o] + cur[i + 1:]
            write_tas(tmp, trial, ["tidy"])
            e = replay(bdir, tmp)
            if e is not None and e <= best:
                cur = trial
                break
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("room")
    ap.add_argument("--tas", help="start from this route instead of running the beam search")
    ap.add_argument("--from-frame", type=int, default=0,
                    help="keep the first K frames of the best route fixed and optimise the rest")
    ap.add_argument("--beam-width", type=int, default=50000)
    ap.add_argument("--timeout", type=float, default=1800, help="seconds per SAT query")
    ap.add_argument("--out", help="output directory (default build/<room>)")
    ap.add_argument("--no-sat", action="store_true",
                    help="skip the SAT descent (just replay, tidy and write outputs)")
    a = ap.parse_args()

    name = os.path.splitext(os.path.basename(a.room))[0]
    bdir = os.path.abspath(a.out or f"{ROOT}/build/{name}")
    build(a.room, bdir)

    # 1. upper bound
    if a.tas:
        inc = read_tas(a.tas)
        src = a.tas
    else:
        t0 = time.time()
        r = sh([f"{bdir}/beam", "-k", str(a.beam_width), f"{bdir}/beam.tas"])
        print(r.stdout.strip(), f"({time.time() - t0:.1f}s)")
        inc = read_tas(f"{bdir}/beam.tas")
        src = "beam search"
    write_tas(f"{bdir}/best.tas", inc, [f"from {src}"])
    best = replay(bdir, f"{bdir}/best.tas")
    if best is None: sys.exit("the starting route does not leave the room")
    inc = inc[:best]
    print(f"upper bound: {best} frames ({src})")

    # 2. fixed prefix
    K = a.from_frame
    start_file = None
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

    # 4. tidy: simplify inputs frame by frame (same frame count, easier to read)
    inc = tidy(bdir, inc, best, K)

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
