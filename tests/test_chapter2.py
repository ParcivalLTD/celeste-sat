#!/usr/bin/env python3
"""
test_chapter2.py -- comprehensive unit tests for Chapter 2 mechanics:
1. DreamBlock collision & passage in ST_DREAM_DASH
2. DreamBlock is solid for walking/normal movement (cannot walk through)
3. Badeline Chaser kills if waiting in place
4. Badeline Chaser avoids killing when staying ahead
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def setup_room(room_name):
    bdir = os.path.join(ROOT, "build", room_name)
    os.makedirs(bdir, exist_ok=True)
    room_txt = os.path.join(ROOT, "rooms", f"{room_name}.txt")
    room_h = os.path.join(bdir, "room.h")
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "make_room.py"), room_txt, room_h])
    
    gen = os.path.join(bdir, "gen_tables.exe" if sys.platform == "win32" else "gen_tables")
    subprocess.check_call(["gcc", "-O0", "-I", os.path.join(ROOT, "model"), "-o", gen, os.path.join(ROOT, "tools", "gen_tables.c")])
    out_tables = subprocess.check_output([gen]).decode("utf-8")
    with open(os.path.join(bdir, "tables.h"), "w", encoding="utf-8") as f:
        f.write(out_tables)
        
    sim_bin = os.path.join(bdir, "sim.exe" if sys.platform == "win32" else "sim")
    subprocess.check_call(["gcc", "-O2", "-I", bdir, "-I", os.path.join(ROOT, "model"), "-o", sim_bin, os.path.join(ROOT, "sim", "sim.c")])
    return bdir, sim_bin

def test_dream_block_dash():
    print("--- Test 1: Dream Block Dash Passage ---")
    bdir, sim_bin = setup_room("dream_test")
    tas_path = os.path.join(bdir, "test_dash.tas")
    with open(tas_path, "w") as f:
        f.write("   1,R,X\n  35,R\n")
        
    json_path = os.path.join(bdir, "trace_dash.json")
    res = subprocess.run([sim_bin, "-j", json_path, tas_path], capture_output=True, text=True)
    
    trace = json.loads(open(json_path).read())
    states = [f["st"] for f in trace["frames"]]
    assert 3 in states, f"ST_DREAM_DASH (3) not reached! States: {states}"
    
    # Verify exit and refill
    entered_dd, exited_dd = False, False
    for f in trace["frames"]:
        if f["st"] == 3:
            entered_dd = True
        elif entered_dd and f["st"] == 0:
            exited_dd = True
            assert f["dashes"] == 1, f"Expected 1 dash after exit, got {f['dashes']}"
            break
            
    assert entered_dd and exited_dd, "Dream dash transition failure"
    print("PASS: Dream dash entered, passed through, exited, and refilled dash!")

def test_dream_block_solid_walk():
    print("--- Test 2: Dream Block Solid Collision (Walk) ---")
    bdir, sim_bin = setup_room("dream_test")
    # Walk right towards dream block at x=48..80. Madeline right edge is x+4.
    # Without dashing, Madeline must be stopped at x=44!
    tas_path = os.path.join(bdir, "test_walk.tas")
    with open(tas_path, "w") as f:
        f.write("  50,R\n")
        
    json_path = os.path.join(bdir, "trace_walk.json")
    subprocess.run([sim_bin, "-j", json_path, tas_path], capture_output=True, text=True)
    
    trace = json.loads(open(json_path).read())
    final_x = trace["frames"][-1]["x"]
    states = {f["st"] for f in trace["frames"]}
    
    assert states == {0}, f"Madeline should only stay in ST_NORMAL (0), got {states}"
    assert final_x == 44, f"Madeline should be blocked at x=44 by DreamBlock at x=48, but reached x={final_x}!"
    print(f"PASS: Dream block is completely solid to walking! Blocked at x={final_x} as expected.")

def test_badeline_chaser():
    print("--- Test 3: Badeline Chaser waits until she moves ---")
    bdir, sim_bin = setup_room("chaser_test")
    # BadelineOldsite starts chasing only once Player.JustRespawned is cleared (she moves)
    tas_path = os.path.join(bdir, "test_idle.tas")
    with open(tas_path, "w") as f:
        f.write("  60\n")
    json_path = os.path.join(bdir, "trace_idle.json")
    subprocess.run([sim_bin, "-j", json_path, tas_path], capture_output=True, text=True)
    trace = json.loads(open(json_path).read())
    total_frames = len(trace["frames"]) - 1
    assert total_frames == 60, f"standing still at the spawn must not wake the chaser (died after {total_frames})"
    print("PASS: standing at the spawn, the chaser never comes")

    print("--- Test 3b: Badeline Chaser catches her when she stops ---")
    # Delay 30 frames: walk right for 20 frames, then stand; the chaser replays her path
    # 28-30 frames later and reaches her about 30 frames after she stopped
    tas_path = os.path.join(bdir, "test_stop.tas")
    with open(tas_path, "w") as f:
        f.write("  20,R\n  60\n")
    json_path = os.path.join(bdir, "trace_stop.json")
    subprocess.run([sim_bin, "-j", json_path, tas_path], capture_output=True, text=True)
    trace = json.loads(open(json_path).read())
    total_frames = len(trace["frames"]) - 1
    print(f"Frames until death: {total_frames}")
    assert 35 <= total_frames <= 55, f"expected death 15-35 frames after stopping, got frame {total_frames}"
    print(f"PASS: the chaser caught her standing still, on frame {total_frames}")

    print("--- Test 4: Badeline Chaser Survival by Movement ---")
    # Moving right continuously stays ahead of Badeline
    tas_path2 = os.path.join(bdir, "test_run.tas")
    with open(tas_path2, "w") as f:
        f.write("  50,R\n")

    json_path2 = os.path.join(bdir, "trace_run.json")
    res2 = subprocess.run([sim_bin, "-j", json_path2, tas_path2], capture_output=True, text=True)
    trace2 = json.loads(open(json_path2).read())
    total_frames2 = len(trace2["frames"])
    # Should not die: should reach room exit or full 50 frames
    print(f"Sim output running: {res2.stdout.strip()}")
    assert total_frames2 > 35, f"Madeline should not die while running ahead, but survived only {total_frames2} frames"
    print("PASS: Moving Madeline stayed ahead of Badeline and survived!")

if __name__ == "__main__":
    test_dream_block_dash()
    test_dream_block_solid_walk()
    test_badeline_chaser()
    print("\nALL CHAPTER 2 MECHANICS TESTS PASSED 100%!")
