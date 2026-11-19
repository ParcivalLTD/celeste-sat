#!/usr/bin/env python3
"""
certify.py -- checked proofs for the "no" answers of tools/windows.py.

    tools/certify.py ROOM ROUTE.tas [--start ENTRY.h] [--width 8] [--jobs 2] [--json OUT.json]
    tools/certify.py --self-check

windows.py asks CBMC, for every K, whether any W inputs take Madeline from
the route's state after K frames to its state after K + W + 1 frames
(harness/window.c), and believes CBMC's answer. This script asks the same
question with the same command, but has CBMC write the formula out as DIMACS
CNF instead of solving it, then:

  1. CBMC solves the window itself, as windows.py does (its verdict);
  2. CaDiCaL solves the CNF and writes a DRAT proof (exit 20 = UNSAT, 10 = SAT);
  3. drat-trim, a separate and much simpler program, checks the proof;
  4. the two verdicts must agree, or the run stops.

A window is "certified" when CBMC says no, CaDiCaL says UNSAT and drat-trim
says "s VERIFIED". Anything else (a yes, a timeout, a proof that does not
check) is recorded as such, never dropped. A window that CBMC proves while
simplifying (no condition left, for instance inside a dash where no input
matters) has an empty CNF: it is recorded as "settled", with no formula to
solve and no proof to check. Each window is one row of the JSON file, written
after every window, so an interrupted run keeps what it did.

What stays trusted is CBMC's translation of harness/window.c into the CNF,
the model, the question, the field mask (sim/live.c) and drat-trim itself:
results/certificates/README.md.

--self-check runs the pipeline where the answers are known: the demo room
`ledge` with a wasted first frame (tests/fixtures/ledge_wasted.tas), whose
first 4-frame window has a faster route (the CNF must be SAT), and whose
second is a "no" that must certify; then it cuts the end off that window's
proof (written as text) and drat-trim must reject it; last, a 2-frame window
that CBMC settles itself must be recorded as settled.

Tools: cbmc, cadical and drat-trim on PATH, or set CBMC, CADICAL, DRAT_TRIM.
drat-trim has no version flag: the SHA-256 of its binary is recorded instead.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat import cbmc  # noqa: E402
from celeste_sat.build import build, replay, sh  # noqa: E402
from celeste_sat.paths import BUILD, ROOT, exe  # noqa: E402
from celeste_sat.tas import read_tas, write_tas  # noqa: E402
from tools.windows import dump, ignored, query  # noqa: E402

CADICAL = os.environ.get("CADICAL", "cadical")
DRAT_TRIM = os.environ.get("DRAT_TRIM", "drat-trim")


class Disagreement(Exception):
    pass


def tool_path(name):
    p = shutil.which(name)
    if not p:
        sys.exit(f"{name} not found (on PATH, or set {'CADICAL' if 'cadical' in name else 'DRAT_TRIM'})")
    return p


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def versions():
    """the tool versions, as recorded with every run"""
    cb = subprocess.run(cbmc.command("--version")[:-2], capture_output=True, text=True).stdout.strip()
    ca = subprocess.run([CADICAL, "--version"], capture_output=True, text=True).stdout.strip()
    dt = tool_path(DRAT_TRIM)
    return {"cbmc": cb, "cadical": ca, "drat-trim": f"binary sha256 {sha256(dt)}"}


def window_args(bdir, k, w, mask):
    """the arguments windows.query() gives CBMC for the window after frame k, without --trace --json-ui"""
    return cbmc.command(f"{ROOT}/harness/window.c", "-I", bdir, "-I", f"{ROOT}/model", "-I", f"{ROOT}/harness",
                        f"-DW={w}", f'-DSTART_STATE_FILE="win_{k}_start.h"',
                        f'-DTARGET_STATE_FILE="win_{k}_target.h"', f"-DSF_IGNORE={mask}u")[:-2]


def export_cnf(bdir, k, w, mask, cnf, timeout):
    """CBMC's formula for the window as DIMACS -> (variables, clauses, seconds, remaining): remaining is
    how many verification conditions CBMC leaves after its own simplification (None if it does not say)"""
    t0 = time.time()
    r = subprocess.run(window_args(bdir, k, w, mask) + ["--dimacs", "--outfile", cnf], cwd=bdir,
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode or not os.path.exists(cnf):
        raise RuntimeError(f"window {k}: cbmc --dimacs failed:\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
    m = re.search(r"(\d+) remaining after simplification", r.stdout)
    remaining = int(m.group(1)) if m else None
    with open(cnf) as f:
        for line in f:
            if line.startswith("p cnf"):
                _, _, v, c = line.split()
                return int(v), int(c), time.time() - t0, remaining
    raise RuntimeError(f"window {k}: no 'p cnf' line in {cnf}")


def solve(cnf, proof, timeout, text_proof=False):
    """CaDiCaL on the CNF, writing a DRAT proof -> ("unsat" | "sat" | "timeout" | "error <code>", seconds)"""
    t0 = time.time()
    cmd = [CADICAL, "-q", "-n"] + (["--no-binary"] if text_proof else []) + [cnf, proof]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout", time.time() - t0
    answer = {20: "unsat", 10: "sat"}.get(r.returncode, f"error {r.returncode}")
    return answer, time.time() - t0


def check(cnf, proof, timeout):
    """drat-trim on the CNF and proof -> ("verified" | "not verified" | "timeout" | "error", seconds)"""
    t0 = time.time()
    try:
        r = subprocess.run([DRAT_TRIM, cnf, proof, "-t", str(timeout)], capture_output=True, text=True,
                           timeout=timeout + 60)
    except subprocess.TimeoutExpired:
        return "timeout", time.time() - t0
    s = [l for l in r.stdout.splitlines() if l.startswith("s ")]
    verdict = {"s VERIFIED": "verified", "s NOT VERIFIED": "not verified", "s TIMEOUT": "timeout"}.get(
        s[-1].strip() if s else "", "error")
    return verdict, time.time() - t0


def certify_window(bdir, k, w, mask, timeout, keep, cbmc_verdict=True):
    """the whole pipeline for one window -> a row of the JSON file. Raises Disagreement when
    CBMC and CaDiCaL answer differently, or when an UNSAT proof does not check."""
    cnf, proof = f"{bdir}/win_{k}.cnf", f"{bdir}/win_{k}.drat"
    row = {"k": k, "frames": [k + 1, k + w + 1], "mask": mask, "ignored": ignored(mask)}
    if cbmc_verdict:
        found, _, dt = query(bdir, k, w, timeout, mask)
        row["cbmc"] = {None: "timeout", False: "no", True: "yes"}[found]
        row["cbmc_seconds"] = round(dt, 1)
    try:
        v, c, dt, remaining = export_cnf(bdir, k, w, mask, cnf, timeout)
    except subprocess.TimeoutExpired:
        row.update(solver="cnf export timeout", certified=False)
        return row
    row.update(variables=v, clauses=c, cnf_seconds=round(dt, 1), cnf_bytes=os.path.getsize(cnf),
               cnf_sha256=sha256(cnf))
    if remaining == 0:
        # CBMC proves the window while simplifying (e.g. inside a dash, where no input matters): no
        # condition is left, so its DIMACS output is the empty formula, which every solver calls SAT.
        # There is nothing to solve and no proof to check; the "no" rests on CBMC alone.
        if row.get("cbmc") == "yes":
            raise Disagreement(f"window {k}: CBMC says yes but leaves no condition after simplification")
        row.update(vccs_remaining=0, solver="not run", settled="by CBMC while simplifying (no formula, no proof)",
                   certified=False)
        if not keep and os.path.exists(cnf):
            os.remove(cnf)
        return row
    answer, dt = solve(cnf, proof, timeout)
    row.update(solver=answer, solver_seconds=round(dt, 1))
    expected = {"no": "unsat", "yes": "sat"}.get(row.get("cbmc"))
    if expected and answer in ("unsat", "sat") and answer != expected:
        raise Disagreement(f"window {k}: CBMC says {row['cbmc']}, CaDiCaL says {answer}")
    if answer == "unsat":
        row.update(proof_bytes=os.path.getsize(proof), proof_sha256=sha256(proof))
        verdict, dt = check(cnf, proof, timeout)
        row.update(checker=verdict, checker_seconds=round(dt, 1))
        if verdict == "not verified":
            raise Disagreement(f"window {k}: CaDiCaL says UNSAT but drat-trim rejects its proof")
    row["certified"] = row.get("cbmc", "no") == "no" and answer == "unsat" and row.get("checker") == "verified"
    if not keep:
        for p in (cnf, proof):
            if os.path.exists(p):
                os.remove(p)
    return row


def prepare(room, route_path, start, bdir):
    """build the room and replay the route -> (exit frame, path of the route in bdir)"""
    build(room, bdir, start)
    flags = ['-DSTART_STATE_FILE="entry.h"'] if start else []
    r = sh(["gcc", "-O2", *flags, "-I", bdir, "-I", f"{ROOT}/model", "-o", exe(bdir, "live"), f"{ROOT}/sim/live.c"])
    if r.returncode:
        sys.exit(r.stderr)
    route = os.path.join(bdir, "route.tas")
    frames = read_tas(route_path)
    write_tas(route, frames, ["the known route"])
    n = replay(bdir, route)
    if not n:
        sys.exit(f"{route_path} does not leave {room}")
    return n, route


def headers(bdir, route, k, w, exact):
    """the window's start and target headers -> the field mask sim/live.c finds (0 with exact)"""
    dump(bdir, route, k, f"{bdir}/win_{k}_start.h", "START_STATE")
    dump(bdir, route, k + w + 1, f"{bdir}/win_{k}_target.h", "TARGET_STATE")
    return 0 if exact else int(sh([exe(bdir, "live"), str(k + w + 1), route]).stdout.strip())


def self_check(timeout):
    """the pipeline on windows whose answers are known; exits non-zero on any surprise"""
    bdir = os.path.join(BUILD, "certify_selfcheck")
    room, route_path, w = "rooms/ledge.txt", "tests/fixtures/ledge_wasted.tas", 4
    n, route = prepare(os.path.join(ROOT, room), os.path.join(ROOT, route_path), None, bdir)
    failures = []

    print(f"1. a known yes: {room} with a wasted first frame, window K = 0 of {w} frames "
          "(CBMC must find a route, CaDiCaL must say SAT)", flush=True)
    row = certify_window(bdir, 0, w, headers(bdir, route, 0, w, False), timeout, keep=False)
    print(f"   cbmc {row['cbmc']}, cadical {row['solver']} ({row['variables']} variables, {row['clauses']} clauses)")
    if row["cbmc"] != "yes" or row["solver"] != "sat":
        failures.append("known yes was not SAT")

    print("2. a known no: window K = 1 (must certify)", flush=True)
    row = certify_window(bdir, 1, w, headers(bdir, route, 1, w, False), timeout, keep=True)
    print(f"   cbmc {row['cbmc']}, cadical {row['solver']}, drat-trim {row.get('checker')}, "
          f"proof {row.get('proof_bytes')} bytes")
    if not row["certified"]:
        failures.append("known no did not certify")

    print("3. a broken proof: the same window's proof as text, its last 10% of lines cut off "
          "(drat-trim must not say s VERIFIED)", flush=True)
    cnf, text = f"{bdir}/win_1.cnf", f"{bdir}/win_1.txt.drat"
    answer, _ = solve(cnf, text, timeout, text_proof=True)
    with open(text) as f:
        lines = f.readlines()
    # a DRAT proof of UNSAT ends with the empty clause; cut it and the lemmas before it
    cut = max(1, len(lines) // 10)
    with open(text, "w") as f:
        f.writelines(lines[:-cut])
    verdict, _ = check(cnf, text, timeout)
    print(f"   cadical {answer}, {len(lines)} proof lines, {cut} cut off: drat-trim {verdict}")
    if answer != "unsat" or verdict == "verified":
        failures.append("a truncated proof was accepted")
    for p in (cnf, f"{bdir}/win_1.drat", text):
        if os.path.exists(p):
            os.remove(p)

    print("4. a window CBMC settles itself: K = 2, W = 2 (no condition left after its simplification, "
          "an empty CNF: recorded as settled, not as a disagreement)", flush=True)
    try:
        row = certify_window(bdir, 2, 2, headers(bdir, route, 2, 2, False), timeout, keep=False)
        print(f"   cbmc {row['cbmc']}, {row['variables']} variables, {row.get('settled') or 'cadical ' + row['solver']}")
        if row["cbmc"] != "no" or not row.get("settled") or row["certified"]:
            failures.append("a window CBMC settles itself was not recorded as settled")
    except Disagreement as e:
        print(f"   {e}")
        failures.append("a window CBMC settles itself stopped the run as a disagreement")

    if failures:
        sys.exit("SELF-CHECK FAILED: " + "; ".join(failures))
    print("self-check passed: the pipeline says yes, no, 'proof rejected' and 'no formula' where it should")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("room", nargs="?")
    ap.add_argument("route", nargs="?")
    ap.add_argument("--self-check", action="store_true", help="run the pipeline where the answers are known")
    ap.add_argument("--start", help="state header the room starts from (default: its spawn)")
    ap.add_argument("--width", type=int, default=8, help="free frames per window (default 8)")
    ap.add_argument("--from", dest="k0", type=int, default=0, help="first K (default 0)")
    ap.add_argument("--to", dest="k1", type=int, help="last K (default: the last window before the exit)")
    ap.add_argument("--step", type=int, default=1, help="K increment (default 1)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--timeout", type=int, default=7200, help="seconds per step (CBMC, CaDiCaL, drat-trim)")
    ap.add_argument("--exact", action="store_true", help="compare every field (no liveness test)")
    ap.add_argument("--no-cbmc-verdict", action="store_true",
                    help="skip CBMC's own solve (then nothing checks agreement; certified needs only UNSAT + checked)")
    ap.add_argument("--keep", action="store_true", help="keep the CNF and proof files (they can be hundreds of MB)")
    ap.add_argument("--out", help="build directory (default build/certify_<room>_w<W>)")
    ap.add_argument("--json", help="results file (default results/certificates/<room>_w<W>.json)")
    ap.add_argument("--resume", action="store_true",
                    help="keep the rows already in the results file and run only the windows it lacks")
    a = ap.parse_args()
    for t in ("cbmc", CADICAL, DRAT_TRIM):
        tool_path(t)
    if a.self_check:
        return self_check(a.timeout)
    if not (a.room and a.route):
        ap.error("ROOM and ROUTE are required (or --self-check)")

    name = os.path.splitext(os.path.basename(a.room))[0]
    short = re.sub(r"^\d+[a-z]?_", "", name)
    w = a.width
    bdir = os.path.abspath(a.out or os.path.join(BUILD, f"certify_{name}_w{w}"))
    out = a.json or os.path.join(ROOT, "results", "certificates", f"{short}_w{w}.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    n, route = prepare(a.room, a.route, a.start, bdir)
    k1 = min(a.k1 if a.k1 is not None else n, n - w - 2)
    ks = list(range(a.k0, k1 + 1, a.step))
    print(f"route leaves {name} on frame {n}; certifying {len(ks)} windows of {w} free frames "
          f"(K = {ks[0]}..{ks[-1]}), {a.jobs} at a time", flush=True)
    doc = {"room": a.room, "route": a.route, "start": a.start, "exit": n, "width": w, "exact": a.exact,
           "versions": versions(), "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "windows": []}
    if a.resume and os.path.exists(out):
        with open(out) as f:
            old = json.load(f)
        same = {key: old.get(key) for key in ("room", "route", "start", "exit", "width", "exact")}
        if same != {key: doc[key] for key in same}:
            sys.exit(f"{out} is for another run ({same}); not resuming")
        if old["versions"] != doc["versions"]:
            sys.exit(f"{out} was made with other tool versions ({old['versions']}); not resuming")
        doc["started"] = old["started"]
        doc["windows"] = [r for r in old["windows"] if "disagreement" not in r]
        done = {r["k"] for r in doc["windows"]}
        ks = [k for k in ks if k not in done]
        print(f"resuming: {len(done)} windows already in {out}, {len(ks)} to go", flush=True)
    masks = {k: headers(bdir, route, k, w, a.exact) for k in ks}
    lock = threading.Lock()
    stop = threading.Event()

    def save():
        doc["windows"].sort(key=lambda r: r["k"])
        tmp = out + ".tmp"
        with open(tmp, "w") as f:
            json.dump(doc, f, indent=1)
        os.replace(tmp, out)

    def run(k):
        if stop.is_set():
            return
        try:
            row = certify_window(bdir, k, w, masks[k], a.timeout, a.keep, not a.no_cbmc_verdict)
        except Disagreement as e:
            stop.set()
            with lock:
                doc["windows"].append({"k": k, "disagreement": str(e)})
                save()
            print(f"\n*** DISAGREEMENT: {e} -- stopping; files kept in {bdir}\n", flush=True)
            return
        with lock:
            doc["windows"].append(row)
            save()
        line = f"  frames {k + 1:3d}..{k + w + 1:3d} in {w}: "
        if row.get("settled"):
            line += f"settled {row['settled']}"
        elif row["certified"]:
            line += (f"certified ({row['variables']} vars, {row['clauses']} clauses; cadical {row['solver_seconds']:.0f}s, "
                     f"drat-trim {row['checker_seconds']:.0f}s, proof {row['proof_bytes'] / 1e6:.0f} MB)")
        else:
            line += (f"NOT certified: cbmc {row.get('cbmc', '-')}, cadical {row['solver']}, "
                     f"drat-trim {row.get('checker', '-')}")
        print(line, flush=True)

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        list(ex.map(run, ks))
    doc["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    save()
    rows = [r for r in doc["windows"] if "disagreement" not in r]
    cert = sum(1 for r in rows if r["certified"])
    settled = sum(1 for r in rows if r.get("settled"))
    total = len(rows) + sum(1 for r in doc["windows"] if "disagreement" in r)
    print(f"{cert} of {len(rows)} windows certified, {settled} settled by CBMC without a formula, "
          f"{total - len(rows)} disagreeing (results in {out})")
    if stop.is_set():
        sys.exit(1)


if __name__ == "__main__":
    main()
