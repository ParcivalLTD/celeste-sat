#!/usr/bin/env python3
"""
summary.py -- what the window proofs have shown so far, per room and width.

    python3 hpc/summary.py

Reads build/cert/w<W>/<room>_k<k0>-<k1>/windows.json (finished chunks) and, for
chunks still running or killed, the per-window lines in build/logs/win_*.out.
"proven" = CBMC said no; "faster" = a spliced route that replays faster in the
model (check it in the game before believing it); "check" = CBMC found inputs
but the spliced route was not faster.
"""
import glob, json, os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
res = defaultdict(dict)                 # (room, w) -> k -> verdict
faster = []

search_dirs = [sys.argv[1]] if len(sys.argv) > 1 else [
    os.path.join(ROOT, "results", "leonardo"),
    os.path.join(ROOT, "build", "leonardo"),
    os.path.join(ROOT, "build")
]

seen_logs = set()
for base in search_dirs:
    for log in glob.glob(os.path.join(base, "logs", "win_*.out")):
        bname = os.path.basename(log)
        if bname in seen_logs:
            continue
        seen_logs.add(bname)
        text = open(log).read()
        m = re.search(r"=== (\S+) W=(\d+) ", text)
        if not m:
            continue
        key = (m.group(1), int(m.group(2)))
        for f, line in re.findall(r"frames\s+(\d+)\.\.\s*\d+ in \d+: (.*)", text):
            k = int(f) - 1
            v = ("faster" if line.startswith("YES") else "check" if line.startswith("yes")
                 else "proven" if line.startswith("no") else "timeout")
            res[key][k] = v
            if v == "faster":
                faster.append(f"{key[0]} W={key[1]} K={k}: {line}")

seen_certs = set()
for base in search_dirs:
    for path in glob.glob(os.path.join(base, "cert", "w*", "*", "windows.json")):
        rel = os.path.relpath(path, base)
        if rel in seen_certs:
            continue
        seen_certs.add(rel)
        d = json.load(open(path))
        room = os.path.splitext(os.path.basename(d["room"]))[0].replace("1a_", "")
        for k, r in d["windows"].items():
            if r["found"] is False:
                res[(room, d["width"])][int(k)] = "proven"
            elif r["found"] is None:
                res[(room, d["width"])][int(k)] = "timeout"

print(f"{'room':8s} {'W':>3s} {'windows':>8s} {'proven':>7s} {'timeout':>8s} {'faster':>7s} {'check':>6s}")
for (room, w), ks in sorted(res.items(), key=lambda x: (x[0][1], x[0][0])):
    c = defaultdict(int)
    for v in ks.values():
        c[v] += 1
    print(f"{room:8s} {w:3d} {len(ks):8d} {c['proven']:7d} {c['timeout']:8d} {c['faster']:7d} {c['check']:6d}")
if faster:
    print("\nfaster routes (model only). A window that reaches the room's exit counts too, so most of these\n"
          "are faster *endings* that leave in a different state: check the next room with\n"
          "experiments/next_room.py, and splice same-state ones with tools/splice_tas.py combine:")
    print("\n".join(faster))
