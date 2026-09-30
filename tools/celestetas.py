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


TRANSITION_WAIT = 40   # idle frames after a room's exit frame: the game's transition (measured,
                       # recordings/celeste-sat-probe-1to2.txt; the community TASes wait 40 too)


def chain_segments(path):
    """(room, frames) per room of a chained TAS whose header lists '#   ROOM: N frames'"""
    counts = [(m.group(1), int(m.group(2))) for m in
              (re.match(r"#\s+(\S+):\s+(\d+) frames", l) for l in open(path)) if m]
    if not counts:
        sys.exit(f"{path}: no '#   ROOM: N frames' header lines (write it with tools/chain_chapter2.py)")
    frames, segs, i = read_tas(path), [], 0
    for room, n in counts:
        segs.append((room, frames[i:i + n]))
        i += n
    if i != len(frames):
        sys.exit(f"{path}: the header counts {i} frames, the inputs have {len(frames)}")
    return segs


def chain_check(segs, rdir):
    """replay the rooms in the model, each from the state the previous one leaves her in;
    returns the frame each room is left on (None if it is not)"""
    from chapter import enter_room, exit_side, origin_of, read_state, tables, write_state
    from make_room import parse
    exits, start = [], None
    for k, (room, frames) in enumerate(segs):
        path = os.path.join(rdir, f"{room}.txt")
        bdir = os.path.join(ROOT, "build", "ingame_check", room)
        build(path, bdir, start)
        route = os.path.join(bdir, "route.tas")
        write_tas(route, frames, [room])
        out = subprocess.run([os.path.join(bdir, "sim"), route], capture_output=True, text=True).stdout
        m = re.search(r"EXIT at frame (\d+)", out)
        exits.append(int(m.group(1)) if m else None)
        dead = re.search(r"died at frame (\d+)", out)
        print(f"  {room:12s} {len(frames):4d} frames: " + (f"leaves on frame {m.group(1)}" if m else
              f"dies on frame {dead.group(1)}" if dead else "does not leave"))
        if not m or k + 1 == len(segs):
            break
        exit_h = os.path.join(bdir, "exit.h")
        subprocess.run([os.path.join(bdir, "sim"), "-s", m.group(1), exit_h, route], capture_output=True)
        st = read_state(exit_h)
        nxt = os.path.join(rdir, f"{segs[k + 1][0]}.txt")
        r0, r1 = parse(path)[0], parse(nxt)[0]
        e = enter_room(st, exit_side(st, len(r0[0]) * 8, len(r0) * 8), origin_of(path), origin_of(nxt),
                       len(r1[0]) * 8, len(r1) * 8, tables(bdir))
        start = os.path.join(bdir, "next_entry.h")
        write_state(e, start, f"entering {segs[k + 1][0]} from {room}")
    return exits


def chain(a):
    """a chained route (tools/chain_chapter2.py) as one CelesteTAS file: load the first room,
    play every room's inputs with the transition's idle frames between them, record all of it"""
    segs = chain_segments(a.tas)
    if a.last:
        names = [r for r, _ in segs]
        if a.last not in names:
            sys.exit(f"--last {a.last}: not one of {', '.join(names)}")
        segs = segs[:names.index(a.last) + 1]
    print(f"replaying {len(segs)} rooms in the model:")
    exits = chain_check(segs, a.rooms)
    for (room, frames), ex in zip(segs, exits):
        if ex != len(frames):
            sys.exit(f"{room}: the model leaves on frame {ex}, the route has {len(frames)} frames; "
                     "the chained file does not replay (re-run tools/chain_chapter2.py?)")
    total = sum(len(f) for _, f in segs)
    lines = [
        f"# celeste-sat: {os.path.basename(a.tas)}, {len(segs)} rooms, {total} frames of control "
        f"(+ {TRANSITION_WAIT} per room transition), written by tools/celestetas.py chain",
        f"# loads {a.load}, waits {a.wait} frames"
        + (", skips the cutscene (pause, Skip Cutscene)" if a.skip_cutscene else "")
        + ", then plays every room while recording each frame",
        f"# to {a.dump} in the Celeste folder; check it with python3 tests/recordings.py <that folder>",
        f"console load {a.load}",
        f"{a.wait:4d}",
        *(["   1,S", "   1,D,O", f"{a.skip_wait:4d}"] if a.skip_cutscene else []),
        f"ExportGameInfo, {a.dump}",
    ]
    for k, (room, frames) in enumerate(segs):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".tas", delete=False).name
        write_tas(tmp, frames, [])
        body = [l for l in open(tmp).read().splitlines() if l and not l.startswith("#")]
        os.remove(tmp)
        lines += ["", f"#{room.split('_', 1)[1]} ({len(frames)} frames, leaves on the last)", *body,
                  f"{TRANSITION_WAIT:4d}"]
    if a.after:
        lines.append(f"{a.after:4d}")
    lines += ["EndExportGameInfo", ""]
    open(a.out, "w").write("\n".join(lines))
    print(f"wrote {a.out}: play it in Celeste Studio, then run\n"
          f"  python3 tests/recordings.py <folder with {a.dump}>")


COMMUNITY_URL = ("https://raw.githubusercontent.com/VampireFlower/CelesteTAS/"
                 "098927faa0da3101bf9c2371f1e45d719c830821/1A.tas")


def community(a):
    """the community 1A.tas, recording a stretch of rooms (and, with --entities, entities such as ZipMover)"""
    import urllib.request
    text = open(a.tas).read() if a.tas else urllib.request.urlopen(COMMUNITY_URL, timeout=30).read().decode("utf-8")
    rooms = [r.lstrip("#") for r in a.rooms]
    first, last = rooms[0], rooms[-1]
    replace = {}
    for spec in a.replace or []:                   # ROOM:OLD=NEW1/NEW2/...  (the last line OLD in #ROOM)
        room, rest = spec.split(":", 1)
        old, new = rest.split("=", 1)
        replace[room] = (old.strip(), [l.strip() for l in new.split("/")])
    lines, room, out, started, done = text.splitlines(), None, [], False, False
    # the input lines of each room (the last one is the transition's idle frames)
    last_line = {}
    for i, line in enumerate(lines):
        st = line.strip()
        if re.match(r"#\S", st):
            room = st[1:]
        elif room and re.match(r"\d+", st):
            last_line.setdefault(room, []).append(i)
    room = None
    for i, line in enumerate(lines):
        st = line.strip()
        if re.match(r"#\S", st):
            room = st[1:]
        # start recording at the idle frames that end the room before the first one (its
        # transition), or after the level start's idle frames (the first room from its spawn)
        at_prev = not started and room == prev_room_of(lines, first) and re.fullmatch(r"\d+", st) \
            and i == last_line[room][-1]
        if at_prev and room != "Start":
            out.append(f"ExportGameInfo, {a.dump}" + "".join(f", {e}" for e in a.entities))
            started = True
        if room in replace and st == replace[room][0] and i in last_line[room]:
            out += [f"   {l}" for l in replace[room][1]]
            continue
        out.append(line)
        if at_prev and room == "Start":
            out.append(f"ExportGameInfo, {a.dump}" + "".join(f", {e}" for e in a.entities))
            started = True
        if started and not done and room == last and re.fullmatch(r"\d+", st) and i == last_line[room][-1]:
            out.append("EndExportGameInfo")
            done = True
    if not started:
        sys.exit(f"no room before #{first} in the TAS")
    head = [f"# celeste-sat: community 1A.tas (VampireFlower/CelesteTAS){' with ' + '; '.join(a.replace) if a.replace else ''}",
            f"# records #{first}..#{last} to {a.dump} in the Celeste folder, then plays on to the end of the chapter"]
    open(a.out, "w").write("\n".join(head + out) + "\n")
    print(f"wrote {a.out}: play it with CelesteTAS, then run\n  python3 tests/recordings.py <folder with {a.dump}>")


def prev_room_of(lines, room):
    """the label before #room in the TAS"""
    labels = [l.strip()[1:] for l in lines if re.match(r"#\S", l.strip())]
    k = labels.index(room)
    return labels[k - 1] if k else None


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
    death = trace.get("death_frame", -1)
    return [dict(x=f["x"] + f.get("rx", 0.0), y=f["y"] + f.get("ry", 0.0),
                 vx=f.get("vxe", f["vx"]), vy=f.get("vye", f["vy"]),
                 state="Freeze" if f["frz"] else STATE_NAMES.get(f["st"], str(f["st"])),
                 inp=f["in"], dead=(k + 1 == death),
                 **({k2: f[k2] for k2 in ("zx", "zy", "zt", "lx", "ly") if k2 in f}))
            for k, f in enumerate(frames[1:])], (exit_frame if exit_frame and exit_frame > 0 else None)


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
    m = sub.add_parser("community", help="the community 1A.tas, recording some rooms (and entities)")
    m.add_argument("rooms", nargs="+", help="first and last room to record, e.g. lvl_4 lvl_3b")
    m.add_argument("--tas", help="a local copy of 1A.tas (default: download it at the tested commit)")
    m.add_argument("--entities", nargs="*", default=["ZipMover"], help="entity types to record (default ZipMover)")
    m.add_argument("--replace", action="append", metavar="ROOM:OLD=NEW1/NEW2",
                   help="replace the last input line OLD of ROOM, e.g. 'lvl_3:16,U,X=4,U,X/1,U/9/1,J'")
    m.add_argument("--dump", default="celeste-sat-community.txt")
    m.add_argument("-o", "--out", required=True)
    ch = sub.add_parser("chain", help="a chained route (tools/chain_chapter2.py) as one recorded CelesteTAS file")
    ch.add_argument("tas", help="e.g. build/chapter2_chase/2A_chase.tas")
    ch.add_argument("--load", required=True, help='what follows "console load": chapter and room, e.g. "2 3"')
    ch.add_argument("--wait", type=int, default=300, help="frames to wait after loading (default 300)")
    ch.add_argument("--skip-cutscene", action="store_true",
                    help="after the wait, pause and pick Skip Cutscene (as the community TASes do), e.g. for "
                         "2A room 3, where `console load` starts CS02_BadelineIntro")
    ch.add_argument("--skip-wait", type=int, default=60,
                    help="frames to wait after skipping (default 60; the fade takes ~34)")
    ch.add_argument("--last", help="the last room to play (default: all of them)")
    ch.add_argument("--after", type=int, default=30,
                    help="idle frames recorded in the room after the last (default 30)")
    ch.add_argument("--rooms", default=os.path.join(ROOT, "rooms", "vanilla"))
    ch.add_argument("--dump", default="celeste-sat-chain.txt")
    ch.add_argument("-o", "--out", required=True)
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
    {"export": export, "probe": probe, "community": community, "chain": chain, "show": show,
     "compare": compare}[a.cmd](a)


if __name__ == "__main__":
    main()
