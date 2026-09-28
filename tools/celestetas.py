#!/usr/bin/env python3
"""
celestetas.py -- check a route against the real game with CelesteTAS.

The model has only been checked against itself. This compares it with the
game, frame by frame, using CelesteTAS (an Everest mod) to play the inputs
and record Madeline's exact position (pixel + subpixel), speed and state.

1. Write a CelesteTAS file for a route:

       python3 tools/celestetas.py export rooms/vanilla/1a_lvl_1.txt results/1a_lvl_1.tas \\
           --load "1 lvl_1" -o 1a_lvl_1_check.tas

   It loads the room (`console load`), waits until the respawn animation is
   over and Madeline stands at the spawn in control, then plays the route
   between ExportGameInfo and EndExportGameInfo.

2. Open that file in Celeste Studio and play it. CelesteTAS writes the dump
   (by default `celeste-sat-dump.txt` in the Celeste folder).

3. Compare the dump with the model:

       python3 tools/celestetas.py compare rooms/vanilla/1a_lvl_1.txt results/1a_lvl_1.tas celeste-sat-dump.txt

   It prints the first frame where position, speed or state differ, with the
   frames around it. Any difference is a porting error to fix (or a mechanic
   the model does not cover).
"""
import argparse, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from solve import NOTHING, build, read_tas, write_tas  # noqa: E402

STATE_NAMES = {0: "StNormal", 1: "StClimb", 2: "StDash"}


def export(a):
    frames = read_tas(a.route)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".tas", delete=False).name
    write_tas(tmp, frames, [])
    body = [l for l in open(tmp).read().splitlines() if l and not l.startswith("#")]
    os.remove(tmp)
    lines = [
        f"# celeste-sat route {os.path.basename(a.route)} ({len(frames)} frames), written by tools/celestetas.py",
        "# loads the room, waits until Madeline stands at the spawn in control,",
        f"# then plays the route while recording every frame to {a.dump}",
        f"console load {a.load}",
        f"{a.wait:4d}",
        f"ExportGameInfo, {a.dump}",
        *body,
        "EndExportGameInfo",
        "",
    ]
    open(a.out, "w").write("\n".join(lines))
    print(f"wrote {a.out}: play it with CelesteTAS, then run\n"
          f"  python3 tools/celestetas.py compare {a.room} {a.route} <path to {a.dump}>")


def probe(a):
    """route + idle frames, recorded through the room transition"""
    frames = read_tas(a.route) + [NOTHING] * a.after
    tmp = tempfile.NamedTemporaryFile("w", suffix=".tas", delete=False).name
    write_tas(tmp, frames, [])
    body = [l for l in open(tmp).read().splitlines() if l and not l.startswith("#")]
    os.remove(tmp)
    lines = [
        f"# celeste-sat transition probe: {os.path.basename(a.route)} then {a.after} frames of no input",
        "# records the room transition frame by frame (position, speed, state, room)",
        f"console load {a.load}",
        f"{a.wait:4d}",
        f"ExportGameInfo, {a.dump}",
        *body,
        "EndExportGameInfo",
        "",
    ]
    open(a.out, "w").write("\n".join(lines))
    print(f"wrote {a.out}: play it with CelesteTAS, then run\n"
          f"  python3 tools/celestetas.py show <path to {a.dump}>")


def show(a):
    """print the recorded rows, marking room changes"""
    last_room = None
    for n, line in enumerate(open(a.dump, encoding="utf-8", errors="replace")):
        cols = line.rstrip("\n").split("\t")
        if not cols or cols[0] == "Line" or len(cols) < 7:
            continue
        room = next((c for c in reversed(cols) if c.startswith("[") and c.endswith("]")), "")
        mark = "   <- room change" if last_room is not None and room != last_room else ""
        last_room = room
        if a.frames and not (a.frames[0] <= n <= a.frames[1]):
            continue
        print(f"{n:5d}  {cols[4]:>36}  {cols[5]:>28}  {cols[6]:10} {room}{mark}")


def room_origin(room):
    """the room's top-left corner in world coordinates (the recording's positions are world positions)"""
    for line in open(room):
        m = re.match(r";\s*origin\s+(-?\d+)\s+(-?\d+)", line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return 0, 0


def parse_dump(path, origin=(0, 0)):
    """rows of (inputs, x, y, vx, vy, state, statuses) from an ExportGameInfo file, positions in room coordinates"""
    rows = []
    num = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
    for line in open(path, encoding="utf-8", errors="replace"):
        cols = line.rstrip("\n").split("\t")
        if not cols or cols[0] == "Line" or len(cols) < 7:
            continue
        pos = re.findall(num, cols[4])
        spd = re.findall(num, cols[5])
        if len(pos) < 2 or len(spd) < 2:
            continue
        rows.append(dict(line=cols[0], inputs=cols[1], x=float(pos[0]) - origin[0], y=float(pos[1]) - origin[1],
                         vx=float(spd[0]), vy=float(spd[1]), state=cols[6].strip(),
                         statuses=cols[7] if len(cols) > 7 else "",
                         room=cols[8].strip() if len(cols) > 8 else ""))
    return rows


def row_keys(inputs):
    """the keys held on a recorded frame: "3/  10,R,J" -> "R,J" (the Inputs column shows the TAS line)"""
    line = inputs.split("/", 1)[-1].strip()
    return ",".join(k.strip() for k in line.split(",")[1:] if k.strip())


def model_trace(room, route, start=None):
    """per-frame model states, and the frame the route leaves the room on (or None)"""
    name = os.path.splitext(os.path.basename(room))[0]
    bdir = os.path.join(ROOT, "build", f"check_{name}" + ("_entry" if start else ""))
    build(room, bdir, start)
    tmp = os.path.join(bdir, "route.tas")
    write_tas(tmp, read_tas(route), ["route"])
    subprocess.run([os.path.join(bdir, "sim"), tmp, "-j", os.path.join(bdir, "trace.json")],
                   capture_output=True, text=True)
    trace = json.load(open(os.path.join(bdir, "trace.json")))
    frames = trace["frames"]
    exit_frame = trace.get("exit_frame", -1)
    return [dict(x=f["x"] + f.get("rx", 0.0), y=f["y"] + f.get("ry", 0.0),
                 vx=f.get("vxe", f["vx"]), vy=f.get("vye", f["vy"]),
                 state="Freeze" if f["frz"] else STATE_NAMES.get(f["st"], str(f["st"])),
                 inp=f["in"]) for f in frames[1:]], (exit_frame if exit_frame and exit_frame > 0 else None)


def same(m, g, tol_pos=2e-3, tol_spd=2e-3):
    ok_state = m["state"] == "Freeze" or g["state"] == m["state"]
    return (abs(m["x"] - g["x"]) <= tol_pos and abs(m["y"] - g["y"]) <= tol_pos
            and abs(m["vx"] - g["vx"]) <= tol_spd and abs(m["vy"] - g["vy"]) <= tol_spd and ok_state)


def compare(a):
    origin = room_origin(a.room)
    game = parse_dump(a.dump, origin)
    model, exit_frame = model_trace(a.room, a.route, a.start)
    if not game:
        sys.exit(f"{a.dump}: no player rows found (is it an ExportGameInfo file?)")
    if exit_frame:
        model = model[:exit_frame]

    def agrees(i, j):
        m, g = model[i], game[j]
        if exit_frame and i + 1 == exit_frame:
            # on the exit frame the game has already begun the room transition (speed and control
            # taken over); the position after the frame's movement must still agree
            return (abs(m["x"] - g["x"]) <= 2e-3 and abs(m["y"] - g["y"]) <= 2e-3
                    and "NoControl" in g["statuses"])
        return same(m, g)

    # the recording may start a frame early or late; use the offset that matches longest
    best = (-1, 0)
    for off in range(-3, 4):
        n = 0
        for i in range(len(model)):
            j = i + off
            if j < 0 or j >= len(game) or not agrees(i, j):
                break
            n += 1
        best = max(best, (n, off))
    n, off = best
    total = min(len(model), len(game) - max(off, 0))
    print(f"model: {len(model)} frames" + (f" (leaves the room on frame {exit_frame})" if exit_frame else "")
          + f", game dump: {len(game)} rows, alignment offset {off:+d}"
          + (f", room origin {origin[0]},{origin[1]}" if origin != (0, 0) else ""))
    if n >= len(model):
        print(f"MATCH: all {len(model)} frames agree (position incl. subpixels, speed, state)"
              + (f"; the game starts the room transition on frame {exit_frame} too" if exit_frame else ""))
        return
    print(f"first {n} frames agree; first difference at route frame {n + 1}:")
    print(f"{'frame':>5}  {'in':6} {'model x':>14} {'game x':>14} {'model y':>14} {'game y':>14} "
          f"{'model vx':>11} {'game vx':>11} {'model vy':>11} {'game vy':>11}  state (model/game)")
    for i in range(max(0, n - 3), min(total, n + 5)):
        m, g = model[i], game[i + off] if 0 <= i + off < len(game) else None
        if g is None:
            break
        flag = "  " if agrees(i, i + off) else "<<"
        print(f"{i + 1:5d}  {m['inp']:6} {m['x']:14.6f} {g['x']:14.6f} {m['y']:14.6f} {g['y']:14.6f} "
              f"{m['vx']:11.4f} {g['vx']:11.4f} {m['vy']:11.4f} {g['vy']:11.4f}  {m['state']}/{g['state']} {flag}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("room")
    e.add_argument("route")
    e.add_argument("--load", required=True, help='what follows "console load", e.g. "1 lvl_1"')
    e.add_argument("--wait", type=int, default=300,
                   help="frames to wait after loading (default 300; the chapter's first room plays a long intro)")
    e.add_argument("--dump", default="celeste-sat-dump.txt", help="file CelesteTAS writes the recording to")
    e.add_argument("-o", "--out", required=True)
    p = sub.add_parser("probe", help="route + idle frames through the room transition")
    p.add_argument("room")
    p.add_argument("route")
    p.add_argument("--load", required=True)
    p.add_argument("--wait", type=int, default=300)
    p.add_argument("--after", type=int, default=90, help="idle frames after the route (default 90)")
    p.add_argument("--dump", default="celeste-sat-probe.txt")
    p.add_argument("-o", "--out", required=True)
    w = sub.add_parser("show", help="print a recording, marking room changes")
    w.add_argument("dump")
    w.add_argument("--frames", type=int, nargs=2, metavar=("FROM", "TO"))
    c = sub.add_parser("compare")
    c.add_argument("room")
    c.add_argument("route")
    c.add_argument("dump")
    c.add_argument("--start", help="state header the room starts from (default: its spawn), e.g. the entry "
                   "state from the previous room written by tools/chapter.py or tests/community_tas.py")
    a = ap.parse_args()
    {"export": export, "probe": probe, "show": show, "compare": compare}[a.cmd](a)


if __name__ == "__main__":
    main()
