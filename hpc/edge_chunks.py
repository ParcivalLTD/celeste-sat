#!/usr/bin/env python3
"""
edge_chunks.py -- split the flagged windows into GitHub Actions jobs.

    python3 hpc/edge_chunks.py hpc/edge_run.json

hpc/edge_flagged_w<W>.json lists the windows of width W of the Chapter 1
certificate that experiments/edge_windows.py could not clear for the current
model (the tiles outside the rooms): {room: [K, ...]}. For W = 16 add the
windows Leonardo never finished (hpc/missing_windows.py --merge). This prints the job
matrix for .github/workflows/edge-windows.yml as JSON: one entry per run of
at most `size` consecutive windows of one room, so tools/windows.py (which
takes a range of K) can prove each run in one call.

The config file (hpc/edge_run.json) has:
    width     the window width W (default 12): reads hpc/edge_flagged_w<W>.json
    rooms     list of rooms to run (default: all)
    size      windows per job (default 6)
    limit     only the first N jobs, 0 for all (default 0)
    parallel  CBMC queries at once in a job (default 2: about 16 GB of RAM per runner;
              a W = 16 query can take more than 7.2 GB, so measure before using 2)
    timeout   seconds per query (default 5400)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def chunks(flagged, rooms, size):
    out = []
    for room in rooms:
        ks = sorted(flagged.get(room, []))
        run = []
        for k in ks + [None]:
            if run and (k is None or k != run[-1] + 1 or len(run) == size):
                out.append({"room": room, "k0": run[0], "k1": run[-1], "name": f"{room}_k{run[0]}-{run[-1]}"})
                run = []
            if k is not None:
                run.append(k)
    return out


def main():
    cfg = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else {}
    width = cfg.get("width", 12)
    flagged = json.load(open(os.path.join(ROOT, "hpc", f"edge_flagged_w{width}.json")))
    rooms = cfg.get("rooms") or list(flagged)
    unknown = [r for r in rooms if r not in flagged]
    if unknown:
        sys.exit(f"unknown rooms: {unknown}")
    jobs = chunks(flagged, rooms, cfg.get("size", 6))
    if cfg.get("limit"):
        jobs = jobs[:cfg["limit"]]
    for j in jobs:
        j["width"] = width
        j["parallel"] = cfg.get("parallel", 2)
        j["timeout"] = cfg.get("timeout", 5400)
    print(json.dumps({"include": jobs}, separators=(",", ":")))
    print(f"W={width}: {len(jobs)} jobs, {sum(j['k1'] - j['k0'] + 1 for j in jobs)} windows", file=sys.stderr)


if __name__ == "__main__":
    main()
