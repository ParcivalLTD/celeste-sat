"""
Recordings from the real game, and the model's trace of the same inputs.

CelesteTAS's ExportGameInfo writes, for every frame it plays, the input of
that frame and Madeline's exact position (pixel + subpixel), speed and state
(tab-separated). parse_dump reads such a file; model_trace replays a route in
the model and gives the same quantities per frame, so the two can be compared
frame by frame (tools/celestetas.py compare, tests/recordings.py).
"""
import json
import os
import re

from .build import build, run_sim
from .paths import BUILD, read_text
from .room import parse
from .tas import read_tas, write_tas

STATE_NAMES = {0: "StNormal", 1: "StClimb", 2: "StDash", 3: "StDreamDash"}   # model/celeste.h ST_*
TOLERANCE = 2e-3          # recordings print positions and speeds with a few decimals


def room_origin(room):
    """the room's top-left corner in world coordinates (recordings use world positions); (0, 0) if unknown"""
    return parse(room).origin or (0, 0)


def parse_dump(path, origin=(0, 0)):
    """rows of (inputs, x, y, vx, vy, state, statuses, room, entities, zip) from an
    ExportGameInfo file, positions relative to `origin`"""
    rows = []
    num = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
    for line in read_text(path, encoding="utf-8", errors="replace").splitlines():
        cols = line.rstrip("\n").split("\t")
        if not cols or cols[0] == "Line" or len(cols) < 7:
            continue
        pos = re.findall(num, cols[4])
        spd = re.findall(num, cols[5])
        if len(pos) < 2 or len(spd) < 2:
            continue
        ents = cols[9] if len(cols) > 9 else ""
        zm = re.search(r"ZipMover(?:\[[^\]]*\])?\s*:?\s*\(?\s*(" + num + r")\s*,\s*(" + num + ")", ents)
        rows.append(dict(line=cols[0], inputs=cols[1], x=float(pos[0]) - origin[0], y=float(pos[1]) - origin[1],
                         vx=float(spd[0]), vy=float(spd[1]), state=cols[6].strip(),
                         statuses=cols[7] if len(cols) > 7 else "",
                         room=cols[8].strip() if len(cols) > 8 else "", entities=ents,
                         zip=(float(zm.group(1)), float(zm.group(2))) if zm else None))
    return rows


def row_keys(inputs):
    """the keys held on a recorded frame: "3/  10,R,J" -> "R,J" (the Inputs column shows the TAS line)"""
    line = inputs.split("/", 1)[-1].strip()
    return ",".join(k.strip() for k in line.split(",")[1:] if k.strip())


def model_bdir(room, start=None):
    """the build directory model_trace uses for a room"""
    name = os.path.splitext(os.path.basename(room))[0]
    return os.path.join(BUILD, f"check_{name}" + ("_entry" if start else ""))


def model_trace(room, route, start=None):
    """per-frame model states for a route, and the frame it leaves the room on (or None)"""
    bdir = model_bdir(room, start)
    build(room, bdir, start)
    tmp = os.path.join(bdir, "route.tas")
    write_tas(tmp, read_tas(route), ["route"])
    run_sim(bdir, tmp, "-j", os.path.join(bdir, "trace.json"))
    trace = json.loads(read_text(os.path.join(bdir, "trace.json")))
    frames = trace["frames"]
    exit_frame = trace.get("exit_frame", -1)
    death = trace.get("death_frame", -1)
    return [dict(x=f["x"] + f.get("rx", 0.0), y=f["y"] + f.get("ry", 0.0),
                 vx=f.get("vxe", f["vx"]), vy=f.get("vye", f["vy"]),
                 state="Freeze" if f["frz"] else STATE_NAMES.get(f["st"], str(f["st"])),
                 inp=f["in"], dead=(k + 1 == death),
                 **({k2: f[k2] for k2 in ("zx", "zy", "zt", "lx", "ly") if k2 in f}))
            for k, f in enumerate(frames[1:])], (exit_frame if exit_frame and exit_frame > 0 else None)


def same(m, g, tol_pos=TOLERANCE, tol_spd=TOLERANCE):
    """does a model frame agree with a recorded one (position, speed, state; freeze frames match any state)?"""
    ok_state = m["state"] == "Freeze" or g["state"] == m["state"]
    return (abs(m["x"] - g["x"]) <= tol_pos and abs(m["y"] - g["y"]) <= tol_pos
            and abs(m["vx"] - g["vx"]) <= tol_spd and abs(m["vy"] - g["vy"]) <= tol_spd and ok_state)


def same_position(m, g, tol=TOLERANCE):
    return abs(m["x"] - g["x"]) <= tol and abs(m["y"] - g["y"]) <= tol
