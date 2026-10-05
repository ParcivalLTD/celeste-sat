#!/usr/bin/env python3
"""
make_tasks.py -- split the Chapter 1 window proofs into array tasks.

    python3 hpc/make_tasks.py --width 12
    python3 hpc/make_tasks.py --width 18 --rooms lvl_1 --timeout 36000

Reads the routes tests/chain_tas.py wrote (build/chain_tas/<room>/route.tas)
and writes build/hpc/tasks_w<W>[_<rooms>].txt, one line per array task:
"room width k0 k1", at most --cores windows each. Every task runs all its
windows at once, so its wall time is its slowest query; small tasks (one
32-core Booster node each) keep the cores a slow query leaves idle few. Memory is requested
at about 0.3 GB per free frame + 0.5 GB per query (tools/cross.py's estimate)
plus 15 %. Prints the sbatch command.
"""
import argparse, math, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from solve import read_tas  # noqa: E402
from tas_endings import ORDER  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--width", type=int, required=True)
ap.add_argument("--cores", type=int, default=32, help="CBMC queries (and cores) per task (default 32: one Booster node)")
ap.add_argument("--timeout", type=int, default=3600, help="seconds per CBMC query (default 3600)")
ap.add_argument("--rooms", help="comma-separated rooms (default: all 19)")
a = ap.parse_args()

w = a.width
rooms = a.rooms.split(",") if a.rooms else ORDER
lines, total = [], 0
for room in rooms:
    route = os.path.join(ROOT, "build", "chain_tas", room, "route.tas")
    if not os.path.exists(route):
        sys.exit(f"{route} missing: run python3 tests/chain_tas.py first")
    n = len(read_tas(route))                 # chain_tas.py checked that it leaves on its last frame
    k1 = n - w - 2                           # tools/windows.py's last window
    count = k1 + 1
    parts = math.ceil(count / a.cores)
    size = math.ceil(count / parts)          # equal chunks rather than one full and one tiny
    for k0 in range(0, count, size):
        lines.append(f"{room} {w} {k0} {min(k0 + size - 1, k1)}")
    total += count

mem = min(480, math.ceil(a.cores * (0.3 * w + 0.5) * 1.15))
hours = a.timeout / 3600 + 0.5               # slowest query + building and dumping states
suffix = "" if not a.rooms else "_" + a.rooms.replace(",", "-")
os.makedirs(os.path.join(ROOT, "build", "hpc"), exist_ok=True)
path = os.path.join(ROOT, "build", "hpc", f"tasks_w{w}{suffix}.txt")
open(path, "w").write("\n".join(lines) + "\n")
print(f"W={w}: {total} windows in {len(lines)} tasks of <= {a.cores} -> {os.path.relpath(path, ROOT)}")
print(f"at most {len(lines) * a.cores * hours:.0f} core-h if every task ran to its time limit")
print(f"sbatch --array=0-{len(lines) - 1} --cpus-per-task={a.cores} --mem={mem}G "
      f"--time={int(hours)}:{int(hours % 1 * 60):02d}:00 "
      f"--export=ALL,TASKS={os.path.relpath(path, ROOT)},TIMEOUT={a.timeout} hpc/windows.sbatch")
