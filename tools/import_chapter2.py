#!/usr/bin/env python3
"""
import_chapter2.py -- export Chapter 2 ('2-OldSite.bin') vanilla rooms for celeste-sat.
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "2-OldSite.bin")
OUT_DIR = os.path.join(ROOT, "rooms", "vanilla")

ROOMS = [
    ("lvl_start", ["lvl_0"]),
    ("lvl_0", ["lvl_1"]),
    ("lvl_1", ["lvl_d0"]),
    ("lvl_d0", ["lvl_d7"]),
    ("lvl_d7", ["lvl_d8"]),
    ("lvl_d8", ["lvl_d3"]),
    ("lvl_3", ["lvl_4"]),
    ("lvl_4", ["lvl_5"]),
    ("lvl_5", ["lvl_6"]),
    ("lvl_6", ["lvl_7"]),
    ("lvl_7", ["lvl_8"]),
    ("lvl_8", ["lvl_9"]),
    ("lvl_9", ["lvl_10"]),
    ("lvl_10", ["lvl_2"]),
    ("lvl_2", ["lvl_11"]),
    ("lvl_11", ["lvl_12b"]),
    ("lvl_12b", ["lvl_12"]),
    ("lvl_12", ["lvl_13"]),
    ("lvl_13", []),
]


def main():
    if not os.path.exists(MAP):
        sys.exit(f"Map file {MAP} not found")
    os.makedirs(OUT_DIR, exist_ok=True)
    for room, tos in ROOMS:
        out = os.path.join(OUT_DIR, f"2a_{room}.txt")
        cmd = [sys.executable, os.path.join(ROOT, "tools", "import_map.py"), MAP, room, "-o", out]
        for t in tos:
            cmd += ["--to", t]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(f"Error importing {room}: {r.stderr.strip()}")
        else:
            print(f"Exported {out}")


if __name__ == "__main__":
    main()
