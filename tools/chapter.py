#!/usr/bin/env python3
"""
chapter.py -- solve rooms in sequence, each starting where the previous one
was left, as in a real run.

    python3 tools/chapter.py rooms/vanilla/1a_lvl_1.txt rooms/vanilla/1a_lvl_2.txt \\
        rooms/vanilla/1a_lvl_3.txt --out build/chapter1 [--polish] [--from-frame-tail 15]

For room 1 Madeline starts at the spawn. Every later room starts from the
state she enters it with (see enter_room), and the route there is searched
from that state. Rooms need an "; origin X Y" line (tools/import_map.py
writes one) so positions can be carried over.

Room entry, from Player.cs (published):
  - BeforeUpTransition: Speed = (0, -105), normal state, AutoJump, full
    variable-jump time, dash cooldown 0.2 s; BeforeDownTransition: normal
    state, Speed.Y = max(0, Speed.Y), no AutoJump or variable jump;
    BeforeSideTransition: nothing.
  - TransitionTo: moves her 1 px per frame to the target; on arrival the
    subpixel remainders are zeroed and the speed rounded to whole numbers.
  - OnTransition: dash and stamina refilled, coyote time and forced move
    cleared, wall-slide timer reset.
Where she stops (Level.cs is not published): going up, 5 px above the new
room's bottom edge (feet at H - 5, as a 4 px pad inside the room gives) --
except in rooms 184 px tall (a screen plus 4 px, the usual height), where it
is 9 px (H - 9). Both are measured with CelesteTAS recordings
(recordings/celeste-sat-probe-up-*.txt: seven different ways of leaving
lvl_1, from y = 0 to 5, dashing, ducking or not, all stop at H - 9 in lvl_2;
recordings/celeste-sat-community-lvl4.txt: H - 9 in lvl_4 and lvl_3b, H - 5
in lvl_5, which is 288 px tall), and the community TAS's lvl_7 (216 px) only
works from H - 5, as do lvl_10a, lvl_12 and lvl_11 (224, 232, 264 px). Why
the short rooms differ is not known (the camera, which can only move 4 px
there, is a guess).
Sideways and downwards the stop point is still inferred: 4 px inside the
edge she crossed (12 px when she falls in from above).
The transition itself takes a fixed time (the TAS waits 40 frames) and is
not counted in the frames.
"""
import argparse, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from make_room import parse  # noqa: E402
from solve import read_tas, write_tas  # noqa: E402

ST_NORMAL, ST_CLIMB, ST_DASH = 0, 1, 2
FLOAT_FIELDS = {"remX", "remY", "spdX", "spdY", "beforeDashSpdX", "beforeDashSpdY", "varJumpSpeed",
                "wallSpeedRetained", "maxFall", "stamina", "liftSpeedX", "liftSpeedY", "liftLastX", "liftLastY"}


def origin_of(room_path):
    for line in open(room_path):
        m = re.match(r";\s*origin\s+(-?\d+)\s+(-?\d+)", line)
        if m:
            return int(m.group(1)), int(m.group(2))
    sys.exit(f"{room_path}: no '; origin X Y' line (re-export it with tools/import_map.py)")


def read_state(path):
    """the fields of a START_STATE header written by sim -s"""
    st = {}
    for m in re.finditer(r"\.(\w+)\s*=\s*(\{[^}]*\}|[^,\n]+),", open(path).read()):
        name, v = m.group(1), m.group(2).strip()
        if v.startswith("{"):                       # an array (zipTimer)
            st[name] = [int(x) for x in v.strip("{}").split(",") if x.strip()]
        else:
            st[name] = float.fromhex(v.rstrip("f")) if name in FLOAT_FIELDS else int(v)
    return st


def write_state(st, path, note):
    lines = [f"/* {note} */", "#define START_FRAMES 0", "static const State START_STATE = {"]
    for k, v in st.items():
        if isinstance(v, list):
            lines.append(f"    .{k} = {{{', '.join(str(int(x)) for x in v)}}},")
        else:
            lines.append(f"    .{k} = {float(v).hex()}f," if k in FLOAT_FIELDS else f"    .{k} = {int(v)},")
    lines.append("};")
    open(path, "w").write("\n".join(lines) + "\n")


def tables(bdir):
    k = {}
    for line in open(os.path.join(bdir, "tables.h")):
        m = re.match(r"#define K_(\w+) (\d+)", line)
        if m:
            k[m.group(1)] = int(m.group(2))
    return k


def round_even(v):
    return int(round(v))           # Python rounds halves to even, like Math.Round


def exit_side(st, room_w, room_h):
    h = 6 if st["ducking"] else 11
    if st["x"] - 4 < 0: return "left"
    if st["x"] + 4 > room_w: return "right"
    if 2 * st["y"] - h < 0: return "up"
    return "down"


TRANSITION_GAP = 40      # game frames between the exit frame's update and her first update in
                         # the new room (recordings/celeste-sat-probe-1to2.txt)


def carry_chaser_history(e, st, dx, dy, x, y):
    """the chasers' history of her positions, continued into the new room: the
    old room's frames (in new-room coordinates), then TRANSITION_GAP frames at
    the entry position; chaserTimer = its length, so hist[(chaserTimer-1-j) & mask]
    is j frames ago"""
    hx, hy, t = st.get("histX"), st.get("histY"), st.get("chaserTimer", 0)
    if not hx:
        return
    n = len(hx)
    if t > 0:
        past = [(hx[(t - 1 - j) % n] + dx, hy[(t - 1 - j) % n] + dy) for j in range(n)][::-1]
    else:                                              # no chaser in the old room: nothing recorded
        past = [(x, y)] * n
    seq = (past + [(x, y)] * TRANSITION_GAP)[-n:]
    e["histX"], e["histY"], e["chaserTimer"] = [p[0] for p in seq], [p[1] for p in seq], n


def up_stop(new_h):
    """where her feet stop after an upward transition into a room new_h px tall"""
    return new_h - 9 if new_h <= 184 else new_h - 5


def enter_room(st, side, old_origin, new_origin, new_w, new_h, K):
    """the state after the transition into the next room (see the module doc)"""
    e = dict(st)
    x = st["x"] + old_origin[0] - new_origin[0]
    y = st["y"] + old_origin[1] - new_origin[1]

    def to_normal():
        if e["state"] == ST_DASH:
            e["coActive"], e["coWait"] = 0, 0          # coroutine cancelled
        if e["state"] == ST_CLIMB:
            e["wallSpeedRetentionTimer"] = 0           # ClimbEnd
        if e["state"] != ST_NORMAL:
            e["maxFall"] = 160.0                       # NormalBegin
            e["state"] = ST_NORMAL

    if side == "up":                                   # Player.BeforeUpTransition
        e["spdX"] = 0.0
        e["spdY"] = e["varJumpSpeed"] = -105.0
        to_normal()
        e["autoJump"] = 1
        e["varJumpTimer"], e["varJumpLong"], e["varJumpShort"] = K["VAR_JUMP_TIME"], 0, 0
        e["dashCooldownTimer"] = K["DASH_COOLDOWN"]
    elif side == "down":                               # Player.BeforeDownTransition
        to_normal()
        e["spdY"] = max(0.0, e["spdY"])
        e["autoJump"] = 0
        e["varJumpTimer"] = 0
    # Level.TransitionRoutine target: going up, her feet stop 5 px above the bottom edge,
    # 9 px in rooms 184 px tall (both measured, see above); the other sides inferred (4 px
    # inside the edge crossed, 12 px when falling in)
    if side == "up":
        y = min(y, up_stop(new_h))
    elif side == "down":
        y = max(y, 12)
    elif side == "right":
        x = max(x, 4)
    elif side == "left":
        x = min(x, new_w - 5)
    if side in ("left", "right"):
        y = min(y, new_h - 1)
    # Player.TransitionTo on arrival
    e["x"], e["y"] = x, y
    e["remX"] = e["remY"] = 0.0
    e["spdX"], e["spdY"] = float(round_even(e["spdX"])), float(round_even(e["spdY"]))
    # Player.OnTransition
    e["wallSlideTimer"] = 0                            # WallSlideTime (the solver build counts steps since set)
    e["jumpGraceTimer"] = 0
    e["forceMoveXTimer"] = 0
    e["dashes"] = 1                                    # RefillDash (MAX_DASHES)
    e["stamina"] = 110.0                               # RefillStamina
    # buttons released during the transition; buffers long expired
    for k in ("prevJump", "prevDash", "prevCDash", "jumpBuf", "dashBuf", "cdashBuf", "jumpEdge", "dashEdge",
              "cdashEdge", "demoDashed", "exited", "dead", "freezeTimer",
              "dreamDashCanEndTimer", "dreamJump"):
        e[k] = 0
    # Badeline chasers follow the positions she recorded (Player.ChaserStates) with a
    # delay in game time, across rooms; the transition's frames have no player
    # updates, so they stand for where she enters (see chaser_update in celeste.c)
    carry_chaser_history(e, st, old_origin[0] - new_origin[0], old_origin[1] - new_origin[1], x, y)
    # a new room: its moving solids start over; the lift speed stays with her
    # (Actor.LiftSpeed is not reset by the transition, only by her updates)
    e["zipTimer"] = [0] * len(e.get("zipTimer", [0, 0, 0, 0]))
    e["fbT"] = [0] * len(e.get("fbT", [0, 0, 0, 0]))
    e["crT"] = [0] * len(e.get("crT", [0] * 8))
    e["dbBroken"] = 0
    e["tsOn"] = 0
    e["hopZip"] = e["hopZipT"] = 0
    e["refillTimer"] = [0] * len(e.get("refillTimer", [0] * 8))
    return e


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rooms", nargs="+")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "chapter"))
    ap.add_argument("--polish", action="store_true", help="polish each room's beam route")
    ap.add_argument("--sat-tail", type=int, default=0,
                    help="also prove each route's last N frames optimal (CBMC; 12-16 is practical)")
    ap.add_argument("--beam-width", type=int, default=100000)
    ap.add_argument("--routes", help="comma-separated routes to use instead of searching, one per room "
                                     "('-' = search), e.g. results/1a_lvl_1.tas,-,-")
    a = ap.parse_args()
    given = (a.routes.split(",") if a.routes else []) + ["-"] * len(a.rooms)
    os.makedirs(a.out, exist_ok=True)

    entry, summary, all_frames = None, [], []
    for i, room in enumerate(a.rooms):
        name = os.path.splitext(os.path.basename(room))[0]
        rdir = os.path.join(os.path.abspath(a.out), name)
        cmd = [sys.executable, os.path.join(ROOT, "tools", "solve.py"), room, "--out", rdir,
               "--beam-width", str(a.beam_width), "--keep-exit"]
        if entry:
            cmd += ["--start", entry]
        if a.polish:
            cmd += ["--polish"]
        # first a route (no SAT), then optionally the SAT tail from that route
        if given[i] != "-":
            cmd += ["--tas", os.path.abspath(given[i])]
        r = subprocess.run(cmd + ["--no-sat"], capture_output=True, text=True)
        best = os.path.join(rdir, "best.tas")
        if r.returncode or not os.path.exists(best):
            sys.exit(f"{name}: no route found\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
        frames = read_tas(best)
        n = json.load(open(os.path.join(rdir, "result.json")))["frames"]
        proven = ""
        if a.sat_tail and n > a.sat_tail:
            route_copy = os.path.join(a.out, f"{name}_route.tas")
            write_tas(route_copy, frames[:n], [name])
            base = [c for c in cmd if c != "--polish"]
            if "--tas" in base:
                j = base.index("--tas"); del base[j:j + 2]
            r = subprocess.run(base + ["--tas", route_copy, "--from-frame", str(n - 1 - a.sat_tail)],
                               capture_output=True, text=True)
            res = json.load(open(os.path.join(rdir, "result.json")))
            n, frames = res["frames"], read_tas(best)
            proven = (f"; last {a.sat_tail} frames proven optimal" if res["proven"]
                      else "; SAT tail not finished")
        frames = frames[:n]
        all_frames.append(frames)
        start_note = "spawn" if i == 0 else f"entered from {os.path.basename(a.rooms[i - 1])}"
        print(f"{name}: {n} frames ({start_note}){proven}", flush=True)
        summary.append(dict(room=name, frames=n, start=start_note))

        if i + 1 == len(a.rooms):
            break
        # exit state -> entry state of the next room
        exit_h = os.path.join(rdir, "exit.h")
        subprocess.run([os.path.join(rdir, "sim"), "-s", str(n), exit_h, best], capture_output=True, text=True)
        st = read_state(exit_h)
        rows = parse(room)[0]
        side = exit_side(st, len(rows[0]) * 8, len(rows) * 8)
        nrows = parse(a.rooms[i + 1])[0]
        e = enter_room(st, side, origin_of(room), origin_of(a.rooms[i + 1]),
                       len(nrows[0]) * 8, len(nrows) * 8, tables(rdir))
        entry = os.path.join(os.path.abspath(a.out), f"entry_{i + 2}.h")
        write_state(e, entry, f"entering {os.path.basename(a.rooms[i + 1])} through its "
                              f"{ {'up': 'bottom', 'down': 'top', 'left': 'right', 'right': 'left'}[side]} edge")
        print(f"   -> enters the next room at ({e['x']}, {e['y']}) with speed ({e['spdX']:g}, {e['spdY']:g})", flush=True)

    total = sum(s["frames"] for s in summary)
    combined = [f for fr in all_frames for f in fr]
    write_tas(os.path.join(a.out, "chapter.tas"), combined,
              [f"{len(summary)} rooms, {total} frames of control (transitions not counted)"] +
              [f"  {s['room']}: {s['frames']} frames" for s in summary])
    json.dump(dict(rooms=summary, total=total), open(os.path.join(a.out, "chapter.json"), "w"), indent=1)
    print(f"total: {total} frames ({total / 60:.2f} s) of control over {len(summary)} rooms")


if __name__ == "__main__":
    main()
