#!/usr/bin/env python3
"""
cross.py -- look for a faster route across a room transition.

    python3 tools/cross.py ROOM_A ROUTE_A ROOM_B ROUTE_B [--start ENTRY_A.h]
                           --keep K --target M [--save 1] [--timeout 1800] [--jobs N]

A known route goes through room A (ROUTE_A, leaving on frame nA) and then
room B (ROUTE_B). Keep its first K frames in A fixed, and let everything
after them be free: the rest of A, the transition, and B's first frames.
The question for CBMC: can Madeline be in exactly the state the known route
has after M frames in B, SAVE frames sooner? That state decides everything
after it (model/state_eq.h), so a yes is a route through the transition
that is SAVE frames faster overall, with the rest of B unchanged; a no for
every split of the free frames between A and B proves there is none.

This matters where rooms are optimised one at a time: the fastest way out of
A is not necessarily the fastest way through A and B together (the entry
into B carries A's speed, facing and pending wall-speed retention).

Rooms need an "; origin X Y" line (tools/import_map.py writes one). The
known route's entry into B is computed as in tools/chapter.py; this tool
checks that its C port (model/transition.h) agrees.
"""
import argparse, json, os, re, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from chapter import enter_room, exit_side, origin_of, read_state, tables  # noqa: E402
from make_room import parse  # noqa: E402
from solve import build, carries_lift, read_tas, write_tas  # noqa: E402

SIDES = {"up": "TR_UP", "down": "TR_DOWN", "left": "TR_LEFT", "right": "TR_RIGHT"}


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def state_block(header_path, name):
    """the initializer of a START_STATE header, renamed"""
    text = open(header_path).read()
    body = text[text.index("{"):text.rindex("}") + 1]
    return f"static const State {name} = {body};\n"


def model_unit(path, prefix, room_header):
    open(path, "w").write(f"""/* {os.path.basename(path)}: the model built for one room ({room_header}), written by tools/cross.py */
#ifdef CROSS_CBMC
#define MODEL_ASSUME(c) __CPROVER_assume(c)
#ifndef NO_SYMMETRY
#define FRAME_HOOK(s, in) __CPROVER_assume(!(in).grab || grab_can_matter(s))
#endif
#else
#include <assert.h>
#define MODEL_ASSUME(c) assert(c)
#endif
#define ROOM_HEADER "{room_header}"
#define MODEL_PREFIX {prefix}
#include "celeste.c"
""")


def setup(where, start_block, target_block, tr):
    """cross_setup.h: where A starts, the state to reach in B, the transition (A_STEPS/B_STEPS come with -D).
    The queries read OUT/cross_setup.h, the replay program (sim/chain.c) OUT/replay/cross_setup.h."""
    os.makedirs(where, exist_ok=True)
    open(os.path.join(where, "cross_setup.h"), "w").write(
        "/* written by tools/cross.py */\n"
        f"#define TR_SIDE {tr['side']}\n#define TR_DX {tr['dx']}\n#define TR_DY {tr['dy']}\n"
        f"#define TR_NEW_W {tr['w']}\n#define TR_NEW_H {tr['h']}\n"
        + ("#define ANY_ZIPMOVERS 1\n" if tr.get("zips") else "")
        + start_block.replace("START_STATE", "START") + target_block.replace("START_STATE", "TARGET"))


def compile_chain(out):
    r = sh(["gcc", "-O2", "-I", f"{out}/replay", "-I", out, "-I", f"{ROOT}/model", "-I", f"{ROOT}/sim", "-o", f"{out}/chain",
            f"{ROOT}/sim/chain.c", f"{out}/model_a.c", f"{out}/model_b.c"])
    if r.returncode:
        sys.exit(r.stderr)


def chain(out, route, *extra):
    r = sh([f"{out}/chain", route, *extra])
    info = {}
    for key, pat in (("exitA", r"left room A on frame (-?\d+)"), ("hit", r"state reached on frame (-?\d+)"),
                     ("exitB", r"EXIT at frame (\d+)")):
        m = re.search(pat, r.stdout)
        info[key] = int(m.group(1)) if m else None
    return info


def cbmc_cmd(out, a_steps, b_steps):
    return ["cbmc", f"{ROOT}/harness/cross.c", f"{out}/model_a.c", f"{out}/model_b.c", "-I", out,
            "-I", f"{ROOT}/model", "-I", f"{ROOT}/harness", "-DCROSS_CBMC",
            f"-DA_STEPS={a_steps}", f"-DB_STEPS={b_steps}", "--trace", "--json-ui"]


def cbmc_result(path):
    """(True, frames) when CBMC found a route, (False, None) when it proved there is none"""
    text = open(path).read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        sys.exit(f"could not parse CBMC output ({path}):\n" + text[-2000:])
    for msg in data:
        for res in msg.get("result", []):
            if res["status"] == "SUCCESS":
                return False, None
            if res["status"] == "FAILURE":
                vals = {}
                for st in res.get("trace", []):
                    if st.get("stepType") != "assignment":
                        continue
                    m = re.fullmatch(r"inputs\[(\d+)l?\]\.(mx|my|jump|dash|grab|cdash)", st.get("lhs", ""))
                    if m:
                        d = st["value"]["data"]
                        vals[(int(m.group(1)), m.group(2))] = (d == "TRUE") if d in ("TRUE", "FALSE") else int(d)
                n = 1 + max((i for i, _ in vals), default=-1)
                frames = [(vals.get((i, "mx"), 0), vals.get((i, "my"), 0), vals.get((i, "jump"), 0),
                           vals.get((i, "dash"), 0), vals.get((i, "grab"), False), vals.get((i, "cdash"), 0))
                          for i in range(n)]
                return True, frames
    sys.exit(f"unexpected CBMC output ({path}):\n" + text[-2000:])


def run_queries(out, steps, splits, jobs, timeout, done):
    """one CBMC run per split e (leave A after e free frames), `jobs` at a time, most likely splits first.
    done(e, found, frames, secs) is called as each finishes (found None: timeout); a True return stops the rest."""
    pending, running = list(splits), {}
    try:
        while pending or running:
            while pending and len(running) < jobs:
                e = pending.pop(0)
                log = open(f"{out}/cbmc_{e}.json", "w")
                err = open(f"{out}/cbmc_{e}.err", "w")
                running[e] = (subprocess.Popen(cbmc_cmd(out, e, steps - e), stdout=log, stderr=err), time.time(), log, err)
            time.sleep(0.5)
            for e, (p, t0, log, err) in list(running.items()):
                dt = time.time() - t0
                if p.poll() is None and dt < timeout:
                    continue
                if p.poll() is None:
                    p.kill(); p.wait()
                    found, frames = None, None
                elif p.returncode not in (0, 10):      # 10: CBMC found a route; anything else: it failed
                    log.close(); err.close()
                    sys.exit(f"CBMC failed on the split leaving A after {e} frames (exit code {p.returncode}"
                             + (", killed: out of memory? try --jobs 1" if p.returncode < 0 else "")
                             + f"); see {out}/cbmc_{e}.json and .err")
                else:
                    log.flush()
                    found, frames = cbmc_result(f"{out}/cbmc_{e}.json")
                log.close(); err.close()
                del running[e]
                if done(e, found, frames, dt):
                    return
    finally:
        for p, *_ in running.values():
            p.kill(); p.wait()


def default_jobs(steps):
    """CBMC runs at a time: one per core, as many as fit in free memory (a query takes about
    0.3 GB per free frame, e.g. 4.5 GB for 15 frames)"""
    try:
        avail = int(re.search(r"MemAvailable:\s+(\d+)", open("/proc/meminfo").read()).group(1)) << 10
    except (OSError, AttributeError):
        avail = 8 << 30
    return max(1, min(os.cpu_count() or 1, int(avail / (0.3 * (1 << 30) * steps + (1 << 29)))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("room_a"); ap.add_argument("route_a"); ap.add_argument("room_b"); ap.add_argument("route_b")
    ap.add_argument("--start", help="state header room A starts from (default: its spawn)")
    ap.add_argument("--keep", type=int, required=True, help="frames of room A kept fixed")
    ap.add_argument("--target", type=int, required=True, help="the known route's state after this many frames in B")
    ap.add_argument("--save", type=int, default=1, help="frames to save (default 1)")
    ap.add_argument("--timeout", type=float, default=1800, help="seconds per CBMC query")
    ap.add_argument("--exit-from", type=int, help="skip the splits that leave A before this frame (already "
                    "proven impossible from the same first K frames, e.g. by tools/solve.py --from-frame K)")
    ap.add_argument("--jobs", type=int, help="CBMC queries at a time (default: one per core, as many as fit in free memory)")
    ap.add_argument("--out")
    a = ap.parse_args()

    na_name = os.path.splitext(os.path.basename(a.room_a))[0]
    nb_name = os.path.splitext(os.path.basename(a.room_b))[0]
    out = os.path.abspath(a.out or f"{ROOT}/build/cross_{na_name}_{nb_name}")
    os.makedirs(out, exist_ok=True)

    # single-room builds: the known route in A, its exit state and B's entry (Python rules)
    build(a.room_a, f"{out}/a", a.start)
    route_a, route_b = read_tas(a.route_a), read_tas(a.route_b)
    write_tas(f"{out}/route_a.tas", route_a, ["room A"])
    r = sh([f"{out}/a/sim", f"{out}/route_a.tas"])
    m = re.search(r"EXIT at frame (\d+)", r.stdout)
    if not m:
        sys.exit(f"{a.route_a} does not leave {a.room_a}")
    na = int(m.group(1))
    sh([f"{out}/a/sim", "-s", "0", f"{out}/a_start.h", f"{out}/route_a.tas"])
    sh([f"{out}/a/sim", "-s", str(na), f"{out}/a_exit.h", f"{out}/route_a.tas"])
    st = read_state(f"{out}/a_exit.h")
    rows_a, rows_b = parse(a.room_a)[0], parse(a.room_b)[0]
    any_zips_a = bool(parse(a.room_a)[5])
    any_zips = bool(any_zips_a or parse(a.room_b)[5])            # speed bounds in the harness
    side = exit_side(st, len(rows_a[0]) * 8, len(rows_a) * 8)
    oa, ob = origin_of(a.room_a), origin_of(a.room_b)
    wb, hb = len(rows_b[0]) * 8, len(rows_b) * 8
    entry_py = enter_room(st, side, oa, ob, wb, hb, tables(f"{out}/a"))
    tr = dict(side=SIDES[side], dx=oa[0] - ob[0], dy=oa[1] - ob[1], w=wb, h=hb, zips=any_zips)

    # the two-room program: A and B side by side, the transition in C
    for tag, room in (("a", a.room_a), ("b", a.room_b)):
        r = sh([sys.executable, f"{ROOT}/tools/make_room.py", room, f"{out}/room_{tag}.h"])
        if r.returncode:
            sys.exit(r.stderr)
        # lift boost in B when A can give her a lift speed (zip movers), or in A when she starts with one
        lift_a = bool(a.start and carries_lift(a.start))
        if (tag == "b" and (any_zips_a or lift_a)) or (tag == "a" and lift_a):
            with open(f"{out}/room_{tag}.h", "a") as f:
                f.write("#define CARRIED_LIFT 1\n")
        model_unit(f"{out}/model_{tag}.c", tag, f"room_{tag}.h")
    shutil.copy(f"{out}/a/tables.h", f"{out}/tables.h")
    start0 = state_block(f"{out}/a_start.h", "START_STATE")
    setup(f"{out}/replay", start0, start0, tr)
    compile_chain(out)

    known = route_a[:na] + route_b
    write_tas(f"{out}/known.tas", known, ["the known route through both rooms"])
    info = chain(out, f"{out}/known.tas")
    if info["exitA"] != na or info["exitB"] is None:
        sys.exit(f"the two-room program disagrees with the single-room one: {info}, room A exit {na}")
    total = info["exitB"]
    sh([f"{out}/chain", f"{out}/known.tas", "-s", str(na), f"{out}/b_entry.h"])
    entry_c = read_state(f"{out}/b_entry.h")
    num = lambda v: [float(x) for x in v] if isinstance(v, list) else float(v)
    diff = sorted(k for k in entry_py if k in entry_c and num(entry_py[k]) != num(entry_c[k]))
    if diff:
        sys.exit(f"transition: C and Python disagree on {diff}")
    print(f"known route: leaves {na_name} on frame {na}, {nb_name} on frame {total} "
          f"({total - na} frames there); transition {side}, entry checked (C = Python)")

    K, M, save = a.keep, a.target, a.save
    if not 0 <= K < na or not 1 <= M < total - na:
        sys.exit(f"--keep must be below {na} and --target between 1 and {total - na - 1}")
    sh([f"{out}/chain", f"{out}/known.tas", "-s", str(K), f"{out}/start.h"])
    sh([f"{out}/chain", f"{out}/known.tas", "-s", str(na + M), f"{out}/target.h"])
    start, target = state_block(f"{out}/start.h", "START_STATE"), state_block(f"{out}/target.h", "START_STATE")
    steps = (na - K) + M - save          # free frames in the query
    print(f"free: frames {K + 1}..{na} of {na_name} and the first frames of {nb_name}; target: the known "
          f"state after {M} frames in {nb_name}, {save} frame(s) sooner ({steps} free frames in all)")

    # one query per split: leave A after e free frames, then up to steps - e frames in B
    setup(out, start, target, tr)
    splits = sorted(range(1, steps + 1), key=lambda e: abs(e - (na - K)))
    results = []
    if a.exit_from:
        print(f"  (not asking about leaving {na_name} before frame {a.exit_from}: --exit-from says it cannot be done)")
        results.append(dict(exit_a=f"<{a.exit_from}", answer="no (given)"))
        splits = [e for e in splits if K + e >= a.exit_from]
    jobs = a.jobs or default_jobs(steps)
    print(f"  {len(splits)} CBMC queries (one per frame she could leave {na_name} on), {jobs} at a time")
    better_frames = []

    def done(e, found, frames, dt):
        what = f"  leave {na_name} on frame {K + e}, reach the target within {steps - e} frames of {nb_name}: "
        if found is None:
            print(what + f"timeout after {dt:.0f}s", flush=True)
            results.append(dict(exit_a=K + e, answer="timeout", secs=round(dt)))
            return False
        if not found:
            print(what + f"no ({dt:.0f}s)", flush=True)
            results.append(dict(exit_a=K + e, answer="no", secs=round(dt)))
            return False
        # a faster route: replay it, find where it meets the known route, splice in the rest of B
        cand = known[:K] + frames[:steps]
        write_tas(f"{out}/candidate.tas", cand, ["candidate"])
        setup(f"{out}/replay", start0, target, tr)
        compile_chain(out)
        c = chain(out, f"{out}/candidate.tas", "-t")
        if c["exitB"] is None and (c["hit"] is None or c["hit"] < 0):
            sys.exit(f"model mismatch: CBMC's route does not reach the target in the simulator: {c}")
        cut = c["exitB"] if c["exitB"] else c["hit"]
        better = cand[:cut] + ([] if c["exitB"] else route_b[M:])
        write_tas(f"{out}/better.tas", better, [f"{na_name} + {nb_name}, found by tools/cross.py"])
        b = chain(out, f"{out}/better.tas")
        if b["exitB"] is None or b["exitB"] > total - save:
            sys.exit(f"splicing failed: {b} (known route: {total} frames)")
        print(what + f"yes ({dt:.0f}s): leaves {na_name} on frame {b['exitA']}, {nb_name} on frame {b['exitB']} "
              f"(known: {na}, {total})", flush=True)
        results.append(dict(exit_a=K + e, answer="yes", secs=round(dt), frames=b["exitB"]))
        better_frames.append(b["exitB"])
        return True

    run_queries(out, steps, splits, jobs, a.timeout, done)
    if better_frames:
        json.dump(dict(total=total, better=better_frames[0], results=results), open(f"{out}/result.json", "w"), indent=1)
        print(f"route: {out}/better.tas ({better_frames[0]} frames, known {total})")
        return 0
    proven = all(r["answer"].startswith("no") for r in results)
    json.dump(dict(total=total, results=results, proven=proven), open(f"{out}/result.json", "w"), indent=1)
    print(f"{'proven' if proven else 'not settled'}: no route through frames {K + 1}.. of {na_name} and the "
          f"first {M} frames of {nb_name} saves {save} frame(s)" + ("" if proven else " (some queries timed out)")
          + (f" (given that {na_name} cannot be left before frame {a.exit_from})" if a.exit_from else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
