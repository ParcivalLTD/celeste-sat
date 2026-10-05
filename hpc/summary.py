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
import glob, json, os, re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
res = defaultdict(dict)                 # (room, w) -> k -> verdict
faster = []

for log in glob.glob(os.path.join(ROOT, "build", "logs", "win_*.out")):
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

for path in glob.glob(os.path.join(ROOT, "build", "cert", "w*", "*", "windows.json")):
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
    print("\nfaster routes (model only, check in the game):")
    print("\n".join(faster))
