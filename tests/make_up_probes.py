#!/usr/bin/env python3
"""
make_up_probes.py -- CelesteTAS files that record the upward room transition
from room 1 into room 2 after different ways of leaving room 1.

Where Madeline stops in the new room after going up is measured for one kind
of exit (9 px above the bottom edge, leaving at y = 4-5 in her normal state),
while the community TAS's lvl_5 and lvl_7 only work if she stops 5 px up
after leaving at y = 2 (ducking in one, dashing in the other). Each probe
plays the community TAS's lvl_1 up to a point, leaves the room another way
(the model's exit height, state and ducking in the name), and records 60
more frames: the stop point is where the recorded position settles in [2].

    python3 tests/make_up_probes.py OUTDIR [1A.tas]

The endings were found with the model (y is the height she leaves room 1 at).
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from chain_tas import sections  # noqa: E402

# (tag, lines of the TAS's #lvl_1 kept, ending)
PROBES = [
    ("y2-dash", 15, ["11,K,G", "15,U,X", "60"]),
    ("y2-duck", 14, ["9,K,G", "15,U,Z", "60"]),
    ("y3-dash", 15, ["8,K,G", "15,U,X", "60"]),
    ("y4-dash", 15, ["10,K,G", "15,U,X", "60"]),
    ("y5-dash", 14, ["11,K,G", "15,U,X", "60"]),
    ("y0-duckdash", 15, ["10,K,G", "15,U,Z", "60"]),
    ("y4-normal", 16, ["2", "15,U,X", "1,J", "60"]),
]


def main():
    out = sys.argv[1]
    tas = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "recordings", "1A.tas")
    lvl1 = sections(open(tas).read(), {"lvl_1", "lvl_2"})[0]["lvl_1"]
    os.makedirs(out, exist_ok=True)
    for tag, cut, end in PROBES:
        lines = lvl1[:cut] + end
        body = [f"# celeste-sat transition probe {tag}: room 1 (community TAS, another ending), then 60 idle frames",
                f"# records the transition into room 2 to celeste-sat-probe-up-{tag}.txt",
                "console load 1 lvl_1", " 300", f"ExportGameInfo, celeste-sat-probe-up-{tag}.txt",
                *[f"   {l}" for l in lines], "EndExportGameInfo", ""]
        open(os.path.join(out, f"celeste-sat-probe-up-{tag}.tas"), "w").write("\n".join(body))
        print(f"wrote celeste-sat-probe-up-{tag}.tas")


if __name__ == "__main__":
    main()
