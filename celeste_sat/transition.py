"""
The room transition: the state Madeline enters the next room with.

This is the authoritative version; model/transition.h is its C port (for the
SAT queries across a room boundary, tools/cross.py), and tools/cross.py
checks that the two agree.

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
(data/recordings/celeste-sat-probe-up-*.txt: seven different ways of leaving
lvl_1, from y = 0 to 5, dashing, ducking or not, all stop at H - 9 in lvl_2;
data/recordings/celeste-sat-community-lvl4.txt: H - 9 in lvl_4 and lvl_3b,
H - 5 in lvl_5, which is 288 px tall), and the community TAS's lvl_7 (216 px)
only works from H - 5, as do lvl_10a, lvl_12 and lvl_11 (224, 232, 264 px).
Why the short rooms differ is not known (the camera, which can only move 4 px
there, is a guess).
Sideways and downwards the stop point is still inferred: 4 px inside the
edge she crossed (12 px when she falls in from above).
The transition itself takes a fixed time (the TAS waits 40 frames) and is
not counted in the frames.
"""
import os

from .build import dump_state
from .room import parse
from .state import read_state, tables, write_state

ST_NORMAL, ST_CLIMB, ST_DASH = 0, 1, 2          # model/celeste.h
TRANSITION_GAP = 40      # game frames between the exit frame's update and her first update in
                         # the new room (data/recordings/celeste-sat-probe-1to2.txt)
ENTERED_THROUGH = {"up": "bottom", "down": "top", "left": "right", "right": "left"}


def round_even(v):
    return int(round(v))           # Python rounds halves to even, like Math.Round


def exit_side(st, room_w, room_h):
    """which edge she left a room room_w x room_h px through"""
    h = 6 if st["ducking"] else 11
    if st["x"] - 4 < 0: return "left"
    if st["x"] + 4 > room_w: return "right"
    if 2 * st["y"] - h < 0: return "up"
    return "down"


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
    """the state after the transition into the next room (see the module doc);
    K is the build's timer table (celeste_sat.state.tables)"""
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


def entry_from_exit_state(st, room_path, next_path, K):
    """(entry state dict, side) for the next room, from her state on the frame she left room_path"""
    r0, r1 = parse(room_path), parse(next_path)
    side = exit_side(st, r0.width_px, r0.height_px)
    e = enter_room(st, side, r0.require_origin(), r1.require_origin(), r1.width_px, r1.height_px, K)
    return e, side


def next_entry(bdir, route, n, room_path, next_path, entry_path, note=None, exit_h=None):
    """Play `route` (built in bdir for room_path) to its exit frame n, and write
    the state she enters next_path with to entry_path.
    -> (entry state dict, exit state dict, side)"""
    exit_h = exit_h or os.path.join(bdir, "exit.h")
    dump_state(bdir, route, n, exit_h)
    st = read_state(exit_h)
    e, side = entry_from_exit_state(st, room_path, next_path, tables(bdir))
    write_state(e, entry_path, note or f"entering {os.path.basename(next_path)} through its "
                                       f"{ENTERED_THROUGH[side]} edge")
    return e, st, side
