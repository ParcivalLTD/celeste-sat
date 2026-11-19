#!/usr/bin/env python3
"""
benchmark.py -- the "celeste-window" benchmark family for the SAT Competition.

    tools/benchmark.py [SPEC.json] [--out DIR] [--calibrate SECONDS] [--only NAME ...]

One CNF per (room, route, K, W): CBMC's formula for "can any W inputs take
Madeline from the route's state after K frames to its state after K + W + 1
frames?" (harness/window.c), the same formula tools/certify.py checks. W tunes
the difficulty. Every instance's answer is settled while it is generated:
UNSAT ones carry a DRAT proof checked by drat-trim (certified), SAT ones are
confirmed by CBMC's own counterexample, which windows.py replays in the
simulator.

The spec (default benchmarks/celeste-window/family.json) lists the instances:

    {"family": "celeste-window",
     "instances": [{"room": "rooms/ledge.txt", "route": "results/routes/ledge.tas", "width": 8, "k": 0}, ...]}

For each instance DIR gets <name>.cnf.xz (DIMACS, header counts exact, CBMC's
variable-name comments stripped) and a row in DIR/metadata.json and
DIR/metadata.csv: room, K, W, expected answer, certified, variables,
clauses, SHA-256 of the uncompressed CNF, and, with --calibrate, the
seconds MiniSat, CaDiCaL and Kissat (whichever are installed, or set MINISAT,
CADICAL, KISSAT) take, with that time limit.

Rooms from the game (rooms/vanilla/) are refused unless --allow-game-rooms:
their geometry comes from Celeste's level data, which carries no licence
notice, and the CNFs encode it. The demo rooms in rooms/ are the project's own.
"""
import argparse
import csv
import json
import lzma
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat.paths import BUILD, ROOT  # noqa: E402
from tools.certify import Disagreement, certify_window, headers, prepare, tool_path, versions  # noqa: E402

SOLVERS = {"minisat": os.environ.get("MINISAT", "minisat"), "cadical": os.environ.get("CADICAL", "cadical"),
           "kissat": os.environ.get("KISSAT", "kissat")}


def instance_name(family, inst):
    room = os.path.splitext(os.path.basename(inst["room"]))[0]
    return f"{family}_{room}_w{inst['width']}_k{inst['k']}"


def strip_comments(src, dst, header):
    """copy a DIMACS file without its comment lines, with `header` as the only comments, compressed with xz"""
    with open(src) as f, lzma.open(dst, "wt", preset=6) as g:
        for line in header:
            g.write(f"c {line}\n")
        for line in f:
            if not line.startswith("c"):
                g.write(line)


def run_solver(name, cnf, limit):
    """one solver on the uncompressed CNF -> (answer, seconds); answer None on timeout"""
    exe = shutil.which(SOLVERS[name])
    if not exe:
        return "missing", None
    cmd = {"minisat": [exe, "-verb=0", cnf], "cadical": [exe, "-q", "-n", cnf], "kissat": [exe, "-q", "-n", cnf]}[name]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        return None, round(time.time() - t0, 1)
    return {10: "sat", 20: "unsat"}.get(r.returncode, f"error {r.returncode}"), round(time.time() - t0, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?", default=os.path.join(ROOT, "benchmarks", "celeste-window", "family.json"))
    ap.add_argument("--out", default=os.path.join(BUILD, "benchmark"), help="output directory (default build/benchmark)")
    ap.add_argument("--calibrate", type=int, default=0, metavar="SECONDS",
                    help="time each instance with MiniSat, CaDiCaL and Kissat, with this limit")
    ap.add_argument("--only", nargs="*", help="generate only these instance names")
    ap.add_argument("--timeout", type=int, default=7200, help="seconds per step while settling the answer")
    ap.add_argument("--allow-game-rooms", action="store_true", help="allow rooms from rooms/vanilla/ (see above)")
    a = ap.parse_args()
    for t in ("cbmc", "cadical", "drat-trim"):
        tool_path(os.environ.get(t.upper().replace("-", "_"), t))

    with open(a.spec) as f:
        spec = json.load(f)
    family = spec["family"]
    os.makedirs(a.out, exist_ok=True)
    meta_path = os.path.join(a.out, "metadata.json")
    meta = {"family": family, "versions": versions(), "instances": {}}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta["instances"] = json.load(f).get("instances", {})

    for inst in spec["instances"]:
        name = instance_name(family, inst)
        if a.only and name not in a.only:
            continue
        if "vanilla" in inst["room"].split(os.sep) and not a.allow_game_rooms:
            sys.exit(f"{name}: {inst['room']} is a room from the game; see --allow-game-rooms")
        room, route = os.path.join(ROOT, inst["room"]), os.path.join(ROOT, inst["route"])
        w, k = inst["width"], inst["k"]
        bdir = os.path.join(BUILD, f"benchmark_{name}")
        print(f"{name}: settling the answer ...", flush=True)
        n, broute = prepare(room, route, inst.get("start"), bdir)
        mask = headers(bdir, broute, k, w, inst.get("exact", False))
        try:
            row = certify_window(bdir, k, w, mask, a.timeout, keep=True)
        except Disagreement as e:
            sys.exit(f"{name}: {e}")
        if row.get("settled"):
            sys.exit(f"{name}: CBMC settles this window while simplifying; it has no formula to benchmark")
        expected ={"unsat": "UNSAT", "sat": "SAT"}.get(row["solver"], "UNKNOWN")
        cnf = f"{bdir}/win_{k}.cnf"
        out = os.path.join(a.out, name + ".cnf.xz")
        strip_comments(cnf, out, [
            f"{family}: can W={w} inputs take Madeline from the route's state after K={k} frames",
            f"to its state after K+W+1={k + w + 1} frames? (room {os.path.basename(inst['room'])}, route exits on frame {n})",
            f"expected: {expected}; generated by celeste-sat tools/benchmark.py with {row['variables']} variables"])
        m = {"room": inst["room"], "route": inst["route"], "k": k, "width": w, "mask": mask, "expected": expected,
             "certified": row["certified"], "cbmc": row["cbmc"], "variables": row["variables"],
             "clauses": row["clauses"], "cnf_sha256": row["cnf_sha256"],
             "xz_bytes": os.path.getsize(out), "settle": {key: row.get(key) for key in (
                 "cbmc_seconds", "solver_seconds", "checker", "checker_seconds", "proof_bytes")}}
        if a.calibrate:
            m["calibration"] = {}
            for s in SOLVERS:
                ans, sec = run_solver(s, cnf, a.calibrate)
                m["calibration"][s] = {"answer": ans, "seconds": sec}
                if ans in ("sat", "unsat") and ans.upper() != expected:
                    sys.exit(f"{name}: {s} says {ans}, expected {expected}")
                print(f"   {s}: {ans if ans else 'timeout'} {sec if sec is not None else ''}", flush=True)
        for p in (cnf, f"{bdir}/win_{k}.drat"):
            if os.path.exists(p):
                os.remove(p)
        meta["instances"][name] = m
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=1)
        print(f"   {expected}{' (certified)' if row['certified'] else ''}, {row['variables']} variables, "
              f"{row['clauses']} clauses -> {out}", flush=True)

    with open(os.path.join(a.out, "metadata.csv"), "w", newline="") as f:
        cols = ["name", "room", "k", "width", "expected", "certified", "variables", "clauses", "cnf_sha256"]
        cols += [f"{s}_seconds" for s in SOLVERS]
        wr = csv.writer(f)
        wr.writerow(cols)
        for name, m in sorted(meta["instances"].items()):
            cal = m.get("calibration", {})
            wr.writerow([name] + [m[c] for c in cols[1:9]] + [
                cal.get(s, {}).get("seconds") if cal.get(s, {}).get("answer") not in (None, "missing") else
                ("timeout" if s in cal and cal[s]["answer"] is None else "") for s in SOLVERS])
    print(f"{len(meta['instances'])} instances in {a.out} (metadata.json, metadata.csv)")


if __name__ == "__main__":
    main()
