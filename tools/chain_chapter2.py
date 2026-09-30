#!/usr/bin/env python3
"""
chain_chapter2.py -- solve the Chapter 2 chase rooms in order, each from the
state the previous room leaves her in, and chain them into one route.

    python3 tools/chain_chapter2.py [--beam-width 100000] [--polish]

The first room (2a_lvl_3) starts at its spawn, as `console load 2 3` puts her
there. Every later room starts from the state tools/chapter.py's enter_room
gives her when she crosses into it. A room's solved route is reused only if
it was solved from exactly the same start state (build/<room>/solved_from.h);
otherwise it is searched again.

The chase ends in lvl_13 at the payphone cutscene, which the model has no
goal for, so the chain stops when she enters lvl_13.

Then write the file to play in the game:

    python3 tools/celestetas.py chain build/chapter2_chase/2A_chase.tas \\
        --load "2 3" --dump celeste-sat-2a-chase.txt -o results/celestetas/2a_chase.tas
"""
import argparse, filecmp, json, os, re, shutil, subprocess, sys, time

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
]
SPAWN = "/* the room's spawn */\n"


def sim_path(bdir):
    return os.path.join(bdir, "sim.exe" if sys.platform == "win32" else "sim")


def exit_frame(bdir, tas):
    out = subprocess.run([sim_path(bdir), tas], capture_output=True, text=True).stdout
    m = re.search(r"EXIT at frame (\d+)", out)
    return int(m.group(1)) if m else None


def same_start(bdir, entry):
    """was build/<room>/best.tas solved from this start state?"""
    mark = os.path.join(bdir, "solved_from.h")
    if not os.path.exists(mark) or not os.path.exists(os.path.join(bdir, "best.tas")):
        return False
    if entry is None:
        return open(mark).read() == SPAWN
    return filecmp.cmp(mark, entry, shallow=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--beam-width", type=int, default=100000)
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "chapter2_chase"))
    ap.add_argument("--polish", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    summary, all_inputs, entry = [], [], None
    print(f"=== Chapter 2 chase: {len(CHASE_ROOMS)} rooms, each from the previous room's exit ===", flush=True)

    for idx, room in enumerate(CHASE_ROOMS):
        room_path = os.path.join(ROOT, "rooms", "vanilla", f"{room}.txt")
        bdir = os.path.join(ROOT, "build", room)
        best_tas = os.path.join(bdir, "best.tas")
        t0 = time.time()
        n, status = None, "solved"

        if same_start(bdir, entry):
            build(room_path, bdir, entry)
            n = exit_frame(bdir, best_tas)
            status = "cached"
        if n is None:
            widths = [a.beam_width] + [w for w in (20000, 5000) if w < a.beam_width]
            for bw in widths:
                print(f"[{idx + 1}/{len(CHASE_ROOMS)}] {room:12s}: beam width {bw} ...", flush=True)
                cmd = [sys.executable, os.path.join(ROOT, "tools", "solve.py"), room_path,
                       "--out", bdir, "--beam-width", str(bw), "--no-sat"]
                if entry:
                    cmd += ["--start", entry]
                if a.polish:
                    cmd += ["--polish"]
                r = subprocess.run(cmd, capture_output=True, text=True)
                if os.path.exists(best_tas) and r.returncode == 0:
                    n = exit_frame(bdir, best_tas)
                    if n:
                        break
                print(f"   no route with width {bw}", flush=True)
            if n is None:
                sys.exit(f"{room}: no route found\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
            if entry:
                shutil.copy(entry, os.path.join(bdir, "solved_from.h"))
            else:
                open(os.path.join(bdir, "solved_from.h"), "w").write(SPAWN)

        frames = read_tas(best_tas)[:n]
        print(f"[{idx + 1}/{len(CHASE_ROOMS)}] {room:12s}: {n} frames ({status}, {time.time() - t0:.0f}s)",
              flush=True)
        summary.append({"room": room, "frames": n, "status": status,
                        "start": "spawn" if entry is None else f"entered from {CHASE_ROOMS[idx - 1]}"})
        all_inputs.append(frames)

        # the state she enters the next room with (lvl_13 after the last one)
        nxt = CHASE_ROOMS[idx + 1] if idx + 1 < len(CHASE_ROOMS) else "2a_lvl_13"
        next_path = os.path.join(ROOT, "rooms", "vanilla", f"{nxt}.txt")
        exit_h = os.path.join(bdir, "exit.h")
        route = os.path.join(bdir, "chained.tas")
        write_tas(route, frames, [room])
        subprocess.run([sim_path(bdir), "-s", str(n), exit_h, route], check=True, capture_output=True)
        st = read_state(exit_h)
        r_cur, r_nxt = parse(room_path)[0], parse(next_path)[0]
        side = exit_side(st, len(r_cur[0]) * 8, len(r_cur) * 8)
        e = enter_room(st, side, origin_of(room_path), origin_of(next_path),
                       len(r_nxt[0]) * 8, len(r_nxt) * 8, tables(bdir))
        entry = os.path.join(a.out, f"entry_{nxt}.h")
        write_state(e, entry, f"entering {nxt} from {room}")

    total = sum(s["frames"] for s in summary)
    combined = [f for fr in all_inputs for f in fr]
    out_tas = os.path.join(a.out, "2A_chase.tas")
    write_tas(out_tas, combined,
              [f"Chapter 2 Badeline chase: {len(summary)} rooms, {total} frames ({total / 60:.2f}s) of control, "
               f"room transitions not counted; each room entered from the previous one"] +
              [f"  {s['room']}: {s['frames']} frames" for s in summary])
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump({"rooms": summary, "total_frames": total, "total_seconds": total / 60.0}, f, indent=2)

    print(f"\n=== {len(summary)} rooms: {total} frames ({total / 60:.2f}s) ===\nchained route: {out_tas}")


if __name__ == "__main__":
    main()
