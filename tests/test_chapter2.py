#!/usr/bin/env python3
"""
test_chapter2.py -- the Chapter 2 mechanics on two demo rooms:

  rooms/dream_test.txt    a dream block in an open room
  rooms/chaser_test.txt   a Badeline chaser 30 frames behind

  1. a dash into a dream block enters ST_DREAM_DASH, crosses it, comes out in
     ST_NORMAL and the dash is refilled
  2. without a dash the same block is an ordinary solid: walking stops at it
  3. standing still, the chaser reaches her after about its delay (death)
  4. running away, it does not

These are behaviour checks on the simulator, not a comparison with the real
game: nothing in Chapter 2 has been recorded with CelesteTAS yet (see the
README's "Things to check").  usage: python3 tests/test_chapter2.py
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = ".exe" if sys.platform == "win32" else ""


def build(room):
    """room.h, timer tables and the simulator for one demo room -> (bdir, sim)"""
    bdir = os.path.join(ROOT, "build", f"test_{room}")
    os.makedirs(bdir, exist_ok=True)
    gen = os.path.join(bdir, "gen_tables" + EXE)
    sim = os.path.join(bdir, "sim" + EXE)
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "make_room.py"),
                           os.path.join(ROOT, "rooms", f"{room}.txt"), os.path.join(bdir, "room.h")])
    subprocess.check_call(["gcc", "-O0", "-I", os.path.join(ROOT, "model"), "-o", gen,
                           os.path.join(ROOT, "tools", "gen_tables.c")])
    with open(os.path.join(bdir, "tables.h"), "w") as f:
        f.write(subprocess.check_output([gen]).decode())
    subprocess.check_call(["gcc", "-O2", "-I", bdir, "-I", os.path.join(ROOT, "model"), "-o", sim,
                           os.path.join(ROOT, "sim", "sim.c")])
    return bdir, sim


def run(bdir, sim, name, tas):
    """replay `tas` (CelesteTAS lines) -> the simulator's json trace
    ({"frames": [...], "exit_frame": f, "death_frame": f}; -1 = did not happen)"""
    tas_path = os.path.join(bdir, name + ".tas")
    json_path = os.path.join(bdir, name + ".json")
    open(tas_path, "w").write(tas)
    subprocess.run([sim, "-j", json_path, tas_path], capture_output=True, text=True)
    return json.load(open(json_path))


def test_dream_dash(bdir, sim):
    """a dash into the block: in, through, out, with the dash back"""
    frames = run(bdir, sim, "dream_dash", "   1,R,X\n  35,R\n")["frames"]
    states = [f["st"] for f in frames]
    assert ST_DREAM_DASH in states, f"the dash never entered ST_DREAM_DASH (states: {sorted(set(states))})"
    i = states.index(ST_DREAM_DASH)
    out = next((f for f in frames[i:] if f["st"] == ST_NORMAL), None)
    assert out, "she never came out of the dream block"
    assert out["dashes"] == 1, f"coming out should refill the dash, got {out['dashes']}"
    print(f"  dream dash: entered on frame {i + 1}, out in ST_NORMAL with the dash back")


def test_dream_block_is_solid(bdir, sim):
    """the same block without a dash: an ordinary solid (it starts at x = 48,
    so her right edge at x + 4 stops her at x = 44)"""
    frames = run(bdir, sim, "dream_walk", "  50,R\n")["frames"]
    states = {f["st"] for f in frames}
    assert states == {ST_NORMAL}, f"walking should stay in ST_NORMAL, got {sorted(states)}"
    assert frames[-1]["x"] == 44, f"should be blocked at x = 44, reached x = {frames[-1]['x']}"
    print("  dream block without a dash: solid, walking stops at x = 44")


def test_chaser_catches_her(bdir, sim):
    """standing still in chaser_test (; chaser 30): caught after about 30 frames"""
    t = run(bdir, sim, "chaser_idle", "  50\n")
    assert t["death_frame"] > 0, "standing still in front of the chaser should be fatal"
    assert 28 <= t["death_frame"] <= 36, \
        f"expected the chaser to catch her near frame 31, got {t['death_frame']}"
    print(f"  chaser: caught her on frame {t['death_frame']} standing still")


def test_chaser_outrun(bdir, sim):
    """running away from it: not caught"""
    t = run(bdir, sim, "chaser_run", "  50,R\n")
    assert t["death_frame"] < 0, f"running away should survive, died on frame {t['death_frame']}"
    assert len(t["frames"]) > 36, f"only {len(t['frames'])} frames before the trace stopped"
    print(f"  chaser: outrun for {len(t['frames'])} frames")


ST_NORMAL, ST_DREAM_DASH = 0, 3      # model/celeste.h

if __name__ == "__main__":
    dream = build("dream_test")
    test_dream_dash(*dream)
    test_dream_block_is_solid(*dream)
    chaser = build("chaser_test")
    test_chaser_catches_her(*chaser)
    test_chaser_outrun(*chaser)
    print("Chapter 2 mechanics: all checks passed")
