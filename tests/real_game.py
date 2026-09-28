#!/usr/bin/env python3
"""
real_game.py -- check the model against states recorded in the real game.

The celeste-rl project (github.com/shihaab453/celeste-rl) recorded input
sequences played in Celeste (Steam version, via CelesteTAS) with Madeline's
exact state at some frames. This downloads that recording (it is not copied
into this repository), replays the inputs in the model and compares.

    python3 tests/real_game.py rooms/vanilla/1a_lvl_1.txt

Needs Chapter 1's first room exported from your game (tools/import_map.py).
"""
import json, os, subprocess, sys, tempfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from solve import build, write_tas  # noqa: E402

URL = ("https://raw.githubusercontent.com/shihaab453/celeste-rl/"
       "838cab97947c4f07a2369bf146f4b15cb9da6d04/tests/fixtures/env_replies.json")
ROUTE = "room1_exit_dash_route"      # uses only buttons the model has (no crouch dash)


def main():
    room = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "rooms", "vanilla", "1a_lvl_1.txt")
    data = json.load(urllib.request.urlopen(URL, timeout=30))[ROUTE]
    frames = []
    for a in data["actions"]:
        b, dash_only, move_only = a
        if dash_only or move_only or set(b) - set("LRUDJXG"):
            sys.exit(f"the recording uses an input the model lacks: {a}")
        frames.append((-1 if "L" in b else 1 if "R" in b else 0, -1 if "U" in b else 1 if "D" in b else 0,
                       int("J" in b), int("X" in b), "G" in b, 0))
    bdir = os.path.join(ROOT, "build", "real_game")
    build(room, bdir)
    tas = os.path.join(bdir, "route.tas")
    write_tas(tas, frames, [f"celeste-rl {ROUTE}"])
    subprocess.run([os.path.join(bdir, "sim"), tas, "-j", os.path.join(bdir, "trace.json")], capture_output=True)
    trace = json.load(open(os.path.join(bdir, "trace.json")))
    model = trace["frames"]
    names = {0: "StNormal", 1: "StClimb", 2: "StDash"}
    ok = True
    for sample in data["samples"]:
        step, st = sample["step"], sample.get("state")
        if not st or st.get("RoomName") != "1" or step >= len(model):
            continue
        p, m = st["Player"], model[step]
        game = (p["Position"]["X"] + p["PositionRemainder"]["X"], p["Position"]["Y"] + p["PositionRemainder"]["Y"],
                p["Speed"]["X"], p["Speed"]["Y"], st["PlayerStateName"])
        mine = (m["x"] + m.get("rx", 0), m["y"] + m.get("ry", 0), m.get("vxe", m["vx"]), m.get("vye", m["vy"]),
                names.get(m["st"], "?"))
        same = all(abs(g - v) < 1e-5 for g, v in zip(game[:4], mine[:4])) and game[4] == mine[4]
        ok &= same
        print(f"frame {step:3d}  game ({game[0]:.6f}, {game[1]:.6f}) v=({game[2]:.4f}, {game[3]:.4f}) {game[4]:8}"
              f"  model ({mine[0]:.6f}, {mine[1]:.6f}) v=({mine[2]:.4f}, {mine[3]:.4f}) {mine[4]:8}  {'ok' if same else 'DIFFERENT'}")
    tr = next((s["step"] for s in data["steps"] if any(e["type"] == "transition" for e in s["events"])), None)
    exit_frame = trace.get("exit_frame")
    print(f"room transition: game on frame {tr}, model on frame {exit_frame}  {'ok' if tr == exit_frame else 'DIFFERENT'}")
    ok &= tr == exit_frame
    print("MATCH" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
