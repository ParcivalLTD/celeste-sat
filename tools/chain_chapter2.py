#!/usr/bin/env python3
"""
chain_chapter2.py -- sequentially solve and chain all Chapter 2 chase rooms into an end-to-end TAS.
"""
import argparse, json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from chapter import enter_room, exit_side, origin_of, read_state, tables, write_state  # noqa: E402
from make_room import parse  # noqa: E402
from solve import build, read_tas, write_tas  # noqa: E402

CHASE_ROOMS = [
    "2a_lvl_3",
    "2a_lvl_4",
    "2a_lvl_5",
    "2a_lvl_6",
    "2a_lvl_7",
    "2a_lvl_8",
    "2a_lvl_9",
    "2a_lvl_10",
    "2a_lvl_2",
    "2a_lvl_11",
    "2a_lvl_12b",
    "2a_lvl_12",
    "2a_lvl_13",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start_room", default="2a_lvl_3")
    ap.add_argument("--beam-width", type=int, default=100000)
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "chapter2_chase"))
    ap.add_argument("--polish", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    summary, all_inputs = [], []

    start_idx = CHASE_ROOMS.index(a.start_room) if a.start_room in CHASE_ROOMS else 0
    entry_h = None

    print(f"=== Starting Chapter 2 Automated Chase Pipeline ({len(CHASE_ROOMS)} rooms) ===")

    for idx, room_name in enumerate(CHASE_ROOMS):
        room_path = os.path.join(ROOT, "rooms", "vanilla", f"{room_name}.txt")
        bdir = os.path.join(ROOT, "build", room_name)
        os.makedirs(bdir, exist_ok=True)

        best_tas = os.path.join(bdir, "best.tas")
        sim_exe = os.path.join(bdir, "sim.exe" if sys.platform == "win32" else "sim")

        # If previous entry state exists, use it
        if idx > 0 and not entry_h:
            entry_h = os.path.join(bdir, "entry.h")

        t0 = time.time()
        # Check if already solved
        if os.path.exists(best_tas) and os.path.exists(sim_exe):
            r = subprocess.run([sim_exe, best_tas], capture_output=True, text=True)
            if "EXIT at frame" in r.stdout:
                import re
                m = re.search(r"EXIT at frame (\d+)", r.stdout)
                n = int(m.group(1))
                print(f"[{idx+1}/{len(CHASE_ROOMS)}] {room_name:12s}: already solved ({n} frames)")
                frames = read_tas(best_tas)[:n]
                summary.append({"room": room_name, "frames": n, "status": "cached"})
                all_inputs.append(frames)

                if idx + 1 < len(CHASE_ROOMS):
                    exit_h = os.path.join(bdir, "exit.h")
                    subprocess.run([sim_exe, "-s", str(n), exit_h, best_tas], check=True)
                    st = read_state(exit_h)
                    r_cur = parse(room_path)[0]
                    next_path = os.path.join(ROOT, "rooms", "vanilla", f"{CHASE_ROOMS[idx+1]}.txt")
                    r_nxt = parse(next_path)[0]
                    side = exit_side(st, len(r_cur[0]) * 8, len(r_cur) * 8)
                    e = enter_room(st, side, origin_of(room_path), origin_of(next_path),
                                   len(r_nxt[0]) * 8, len(r_nxt) * 8, tables(bdir))
                    next_bdir = os.path.join(ROOT, "build", CHASE_ROOMS[idx+1])
                    os.makedirs(next_bdir, exist_ok=True)
                    entry_h = os.path.join(next_bdir, "entry.h")
                    write_state(e, entry_h, f"entering {CHASE_ROOMS[idx+1]} from {room_name}")
                continue

        # Solve this room
        print(f"[{idx+1}/{len(CHASE_ROOMS)}] {room_name:12s}: searching with beam (width {a.beam_width})...", flush=True)
        cmd = [sys.executable, os.path.join(ROOT, "tools", "solve.py"), room_path,
               "--out", bdir, "--beam-width", str(a.beam_width), "--no-sat"]
        if entry_h and os.path.exists(entry_h):
            cmd += ["--start", entry_h]
        if a.polish:
            cmd += ["--polish"]

        r = subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.exists(best_tas):
            print(f"ERROR: {room_name} failed to find route!\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")
            break

        # Check exit
        r_sim = subprocess.run([sim_exe, best_tas], capture_output=True, text=True)
        import re
        m = re.search(r"EXIT at frame (\d+)", r_sim.stdout)
        if not m:
            print(f"ERROR: {room_name} route did not exit!\n{r_sim.stdout}")
            break
        n = int(m.group(1))
        dt = time.time() - t0
        print(f"   -> {room_name} solved in {n} frames ({dt:.1f}s)")
        frames = read_tas(best_tas)[:n]
        summary.append({"room": room_name, "frames": n, "time": dt, "status": "solved"})
        all_inputs.append(frames)

        if idx + 1 < len(CHASE_ROOMS):
            exit_h = os.path.join(bdir, "exit.h")
            subprocess.run([sim_exe, "-s", str(n), exit_h, best_tas], check=True)
            st = read_state(exit_h)
            r_cur = parse(room_path)[0]
            next_path = os.path.join(ROOT, "rooms", "vanilla", f"{CHASE_ROOMS[idx+1]}.txt")
            r_nxt = parse(next_path)[0]
            side = exit_side(st, len(r_cur[0]) * 8, len(r_cur) * 8)
            e = enter_room(st, side, origin_of(room_path), origin_of(next_path),
                           len(r_nxt[0]) * 8, len(r_nxt) * 8, tables(bdir))
            next_bdir = os.path.join(ROOT, "build", CHASE_ROOMS[idx+1])
            os.makedirs(next_bdir, exist_ok=True)
            entry_h = os.path.join(next_bdir, "entry.h")
            write_state(e, entry_h, f"entering {CHASE_ROOMS[idx+1]} from {room_name}")

    total_frames = sum(s["frames"] for s in summary)
    combined = [f for fr in all_inputs for f in fr]
    out_tas = os.path.join(a.out, "2A_chase.tas")
    write_tas(out_tas, combined,
              [f"Chapter 2 Badeline Chase: {len(summary)} rooms, {total_frames} frames ({total_frames/60:.2f}s)"] +
              [f"  {s['room']}: {s['frames']} frames" for s in summary])
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump({"rooms": summary, "total_frames": total_frames, "total_seconds": total_frames/60.0}, f, indent=2)

    print(f"\n=== Completed {len(summary)} rooms: {total_frames} frames ({total_frames/60:.2f}s) ===")
    print(f"Combined TAS: {out_tas}")


if __name__ == "__main__":
    main()
