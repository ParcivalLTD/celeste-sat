#!/usr/bin/env python3
"""
chain_chapter2.py -- solve Chapter 2's Badeline chase room after room and
write one TAS for the whole chase.

    python3 tools/chain_chapter2.py [--polish] [--from 2a_lvl_5]

Like tools/chapter.py, but for a fixed room order (CHASE_ROOMS: the way the
chase actually goes through Old Site, which is not the rooms' numeric order)
and with two things the long chase rooms need:

  - rooms already solved are reused (build/<room>/best.tas still replays to an
    exit), so a run can be stopped and resumed;
  - if the full beam width finds no route at all, the room is retried with
    narrower beams. A wide beam keeps many near-duplicate states per frame and
    can crowd out the one line that reaches the exit; a narrow one commits
    earlier. Which width wins is room-dependent, so they are simply tried in
    turn.

No SAT: the chase rooms are far too long for CBMC (see the README's
"Scaling"). This only chains beam routes.
"""
import argparse, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from chapter import enter_room, exit_side, origin_of, read_state, tables, write_state  # noqa: E402
from make_room import parse  # noqa: E402
from solve import read_tas, write_tas  # noqa: E402

CHASE_ROOMS = [
    "2a_lvl_3", "2a_lvl_4", "2a_lvl_5", "2a_lvl_6", "2a_lvl_7", "2a_lvl_8",
    "2a_lvl_9", "2a_lvl_10", "2a_lvl_2", "2a_lvl_11", "2a_lvl_12b",
    "2a_lvl_12", "2a_lvl_13",
]


def room_path(name):
    return os.path.join(ROOT, "rooms", "vanilla", f"{name}.txt")


def build_dir(name):
    d = os.path.join(ROOT, "build", name)
    os.makedirs(d, exist_ok=True)
    return d


def sim_path(bdir):
    return os.path.join(bdir, "sim.exe" if sys.platform == "win32" else "sim")


def exit_frame(sim, tas):
    """the frame the route leaves the room on, or None"""
    r = subprocess.run([sim, tas], capture_output=True, text=True)
    m = re.search(r"EXIT at frame (\d+)", r.stdout)
    return int(m.group(1)) if m else None


def write_entry(cur_name, next_name, bdir, frames):
    """run the exit state of `cur_name` through the transition and write the
    next room's entry.h (the same rules as tools/chapter.py)"""
    exit_h = os.path.join(bdir, "exit.h")
    subprocess.run([sim_path(bdir), "-s", str(frames), exit_h,
                    os.path.join(bdir, "best.tas")], check=True)
    st = read_state(exit_h)
    cur_rows = parse(room_path(cur_name))[0]
    next_rows = parse(room_path(next_name))[0]
    side = exit_side(st, len(cur_rows[0]) * 8, len(cur_rows) * 8)
    e = enter_room(st, side, origin_of(room_path(cur_name)), origin_of(room_path(next_name)),
                   len(next_rows[0]) * 8, len(next_rows) * 8, tables(bdir))
    entry = os.path.join(build_dir(next_name), "entry.h")
    write_state(e, entry, f"entering {next_name} from {cur_name}")
    return entry


def solve_room(name, bdir, entry, widths, polish):
    """beam-search the room, narrowing the beam until a route comes out;
    -> the exit frame, or None if no width found one"""
    for bw in widths:
        print(f"   searching with beam width {bw}...", flush=True)
        cmd = [sys.executable, os.path.join(ROOT, "tools", "solve.py"), room_path(name),
               "--out", bdir, "--beam-width", str(bw), "--no-sat"]
        if entry and os.path.exists(entry):
            cmd += ["--start", entry]
        if polish:
            cmd += ["--polish"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        best = os.path.join(bdir, "best.tas")
        if os.path.exists(best):
            n = exit_frame(sim_path(bdir), best)
            if n is not None:
                return n
        print(f"   (beam width {bw} found no route; {r.stdout[-400:]}{r.stderr[-400:]})")
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start_room", default=CHASE_ROOMS[0],
                    help="re-solve from this room on; the rooms before it must already be solved "
                         "(their build/<room>/best.tas is reused as it is)")
    ap.add_argument("--beam-width", type=int, default=100000)
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "chapter2_chase"))
    ap.add_argument("--polish", action="store_true", help="polish each room's beam route")
    a = ap.parse_args()

    if a.start_room not in CHASE_ROOMS:
        sys.exit(f"unknown room {a.start_room!r}; expected one of {', '.join(CHASE_ROOMS)}")
    os.makedirs(a.out, exist_ok=True)
    widths = [w for w in (a.beam_width, 20000, 5000) if w <= a.beam_width]

    start = CHASE_ROOMS.index(a.start_room)
    print(f"=== Chapter 2 Badeline chase: {len(CHASE_ROOMS)} rooms ===")
    summary, all_inputs, entry = [], [], None
    for idx, name in enumerate(CHASE_ROOMS):
        bdir = build_dir(name)
        best = os.path.join(bdir, "best.tas")
        sim = sim_path(bdir)
        label = f"[{idx + 1}/{len(CHASE_ROOMS)}] {name:12s}"
        t0 = time.time()

        # already solved by an earlier run? reuse it
        n = exit_frame(sim, best) if os.path.exists(best) and os.path.exists(sim) else None
        if n is None and idx < start:
            sys.exit(f"{name}: --from {a.start_room} skips this room, but it has no route in {bdir}")
        if n is not None:
            print(f"{label}: already solved ({n} frames)")
            status, secs = "cached", None
        else:
            print(f"{label}: solving", flush=True)
            n = solve_room(name, bdir, entry, widths, a.polish)
            if n is None:
                print(f"ERROR: {name} found no route at any beam width -- stopping here")
                break
            secs = time.time() - t0
            print(f"   -> {n} frames ({secs:.1f}s)")
            status = "solved"

        summary.append(dict(room=name, frames=n, status=status, time=secs))
        all_inputs.append(read_tas(best)[:n])
        if idx + 1 < len(CHASE_ROOMS):
            entry = write_entry(name, CHASE_ROOMS[idx + 1], bdir, n)

    total = sum(s["frames"] for s in summary)
    out_tas = os.path.join(a.out, "2A_chase.tas")
    write_tas(out_tas, [f for fr in all_inputs for f in fr],
              [f"Chapter 2 Badeline chase: {len(summary)} rooms, {total} frames ({total / 60:.2f}s)"] +
              [f"  {s['room']}: {s['frames']} frames" for s in summary])
    json.dump(dict(rooms=summary, total_frames=total, total_seconds=total / 60.0),
              open(os.path.join(a.out, "summary.json"), "w"), indent=2)
    print(f"\n=== {len(summary)} rooms, {total} frames ({total / 60:.2f}s) ===\n{out_tas}")


if __name__ == "__main__":
    main()
