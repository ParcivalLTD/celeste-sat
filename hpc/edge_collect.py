#!/usr/bin/env python3
"""
edge_collect.py -- what the GitHub Actions rerun of the flagged windows showed.

    python3 hpc/edge_collect.py ARTIFACT_DIR OUT_DIR

ARTIFACT_DIR holds one folder per finished job (edge-<room>_k<k0>-<k1>/, each
with windows.json and run.log, as the workflow uploads them). Copies them to
OUT_DIR/w12/ and prints a markdown summary: per room how many of the flagged
windows are proven ("no"), timed out, found a faster route ("yes"), or never
finished. "Proven" means CBMC (the current model, 5.95) says no input
sequence gets from the route's state at K to its state at K + 13 any faster.
"""
import glob
import json
import os
import re
import shutil
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    flagged = json.load(open(os.path.join(ROOT, "hpc", "edge_flagged_w12.json")))
    got = defaultdict(dict)                                  # room -> K -> windows.json entry
    peak = 0
    for d in sorted(glob.glob(os.path.join(src, "edge-*"))):
        name = os.path.basename(d)[len("edge-"):]
        where = os.path.join(dst, "w12", name)
        os.makedirs(where, exist_ok=True)
        for f in glob.glob(os.path.join(d, "*")):
            shutil.copy(f, where)
        wj = os.path.join(d, "windows.json")
        if os.path.exists(wj):
            j = json.load(open(wj))
            room = os.path.splitext(os.path.basename(j["room"]))[0].replace("1a_", "")
            for k, v in j["windows"].items():
                got[room][int(k)] = v
        log = os.path.join(d, "run.log")
        if os.path.exists(log):
            m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", open(log, errors="replace").read())
            if m:
                peak = max(peak, int(m.group(1)))
    print("| room | flagged | proven (no) | faster (yes) | timeout | missing |")
    print("|---|---|---|---|---|---|")
    tot = defaultdict(int)
    for room, ks in flagged.items():
        r = got.get(room, {})
        no = sum(1 for k in ks if k in r and r[k]["found"] is False)
        yes = sum(1 for k in ks if k in r and r[k]["found"] is True)
        to = sum(1 for k in ks if k in r and r[k]["found"] is None)
        miss = sum(1 for k in ks if k not in r)
        print(f"| {room} | {len(ks)} | {no} | {yes} | {to} | {miss} |")
        for n, v in (("flagged", len(ks)), ("no", no), ("yes", yes), ("timeout", to), ("missing", miss)):
            tot[n] += v
    print(f"| **all** | {tot['flagged']} | {tot['no']} | {tot['yes']} | {tot['timeout']} | {tot['missing']} |")
    print(f"\nlargest single process: {peak / 1048576:.1f} GB")
    json.dump({r: {str(k): v for k, v in sorted(g.items())} for r, g in got.items()},
              open(os.path.join(dst, "w12_all.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
