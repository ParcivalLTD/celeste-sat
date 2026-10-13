#!/usr/bin/env python3
"""
recordings.py -- check the model against recordings made in the real game.

CelesteTAS's ExportGameInfo writes, for every frame it plays, the input of
that frame and Madeline's exact position (pixel + subpixel), speed and
state. This replays each recording's own inputs through the model and
compares every frame, room after room: when she leaves a room, the next one
starts from the state the model gives her on entering it (celeste_sat/transition.py),
at the first frame the game gives control back.

    python3 tests/recordings.py DIR [rooms/vanilla]

DIR is where CelesteTAS wrote the recordings (the Celeste folder, e.g.
/mnt/r/SteamLibrary/steamapps/common/Celeste in WSL); every
celeste-sat-*.txt and community-*.txt there is checked (celeste-sat-2a-*.txt
against the Chapter 2 rooms, the others against Chapter 1). The files in
results/celestetas/ record to such names. A recording that starts in the
middle of the chapter (the community TAS from its #lvl_3, say: name it
community-*.txt) starts from the state the community TAS enters that room
with, which tests/chain_tas.py computes; run that first.

The recordings made so far are in data/recordings/:

    python3 tests/recordings.py data/recordings
"""
import glob
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat.build import replay  # noqa: E402
from celeste_sat.paths import BUILD, VANILLA, read_text, write_text  # noqa: E402
from celeste_sat.recording import (model_bdir, model_trace, parse_dump, room_origin, row_keys,  # noqa: E402
                                   same, same_position)
from celeste_sat.transition import next_entry  # noqa: E402


# The recordings named *-edit* play the community TAS with the 106-frame ending of
# #lvl_3 that SAT found: its last line "16,U,X" replaced (docs/results.md).
EDIT_ROOM, EDIT_NEXT = "lvl_3", "lvl_4"
EDIT_OLD, EDIT_NEW = "16,U,X", ["4,U,X", "1,U", "9", "1,J"]


def edited_entry(room, work):
    """the state she enters `room` with after the edited ending (None if room does not follow it)"""
    if room != EDIT_NEXT:
        return None
    src = os.path.join(BUILD, "chain_tas", EDIT_ROOM)
    lines = read_text(os.path.join(src, "route.tas")).split("\n")
    k = max(i for i, l in enumerate(lines) if l.strip() == EDIT_OLD)
    route = os.path.join(work, "edited.tas")
    write_text(route, "\n".join(lines[:k] + EDIT_NEW + lines[k + 1:]))
    n = replay(src, route)
    entry = os.path.join(work, f"entry_{room}_edit.h")
    next_entry(src, route, n, os.path.join(VANILLA, f"1a_{EDIT_ROOM}.txt"), os.path.join(VANILLA, f"1a_{room}.txt"),
               entry, f"entering {room} after the edited {EDIT_ROOM}", exit_h=os.path.join(work, "edited_exit.h"))
    return entry


def chapter_of(name):
    """the chapter a recording is from, by its name: celeste-sat-2a-*.txt is 2A, anything else 1A"""
    m = re.search(r"-(\d+[abc])-", name.lower())
    return m.group(1) if m else "1a"


def room_file(rdir, tag, chapter="1a"):
    """"[3]" -> rooms/vanilla/1a_lvl_3.txt (2a_lvl_3.txt for Chapter 2)"""
    m = re.fullmatch(r"\[(\w+)\]", tag)
    return os.path.join(rdir, f"{chapter}_lvl_{m.group(1)}.txt") if m else None


def check(path, rdir, work):
    """compare one recording with the model, room after room -> (report line, True / False / None = skipped)"""
    name = os.path.basename(path)
    raw = parse_dump(path)                      # world coordinates
    if not raw:
        return f"{name}: no rows", False
    # split into rooms: runs of rows with the same Room column
    segs, i = [], 0
    while i < len(raw):
        j = i
        while j < len(raw) and raw[j]["room"] == raw[i]["room"]:
            j += 1
        segs.append((raw[i]["room"], i, j))
        i = j
    start, report, ok, frames_checked = None, [], True, 0
    first = segs[0][0]
    if name.startswith("community") or name.startswith("celeste-sat-community"):
        m = re.fullmatch(r"\[(\w+)\]", first)
        if m and m.group(1) != "1":
            # entered as tests/chain_tas.py plays the TAS up to there (after the edit, for a
            # recording of the edited TAS that starts in the room after it)
            start = os.path.join(BUILD, "chain_tas", f"entry_lvl_{m.group(1)}.h")
            if not os.path.exists(start):
                return f"{name}: needs {start} (run tests/chain_tas.py first)", None
            if "-edit" in name and f"lvl_{m.group(1)}" != EDIT_ROOM:
                start = edited_entry(f"lvl_{m.group(1)}", work)
                if not start:
                    return f"{name}: starts in lvl_{m.group(1)}, not after the edited {EDIT_ROOM}", None
    prev = None                                  # (room file, build dir, route file, exit frame)
    for k, (tag, a, b) in enumerate(segs):
        room = room_file(rdir, tag, chapter_of(name))
        if not room or not os.path.exists(room):
            report.append(f"room {tag} is not exported, stopping there")
            break
        rows = raw[a:b]
        if k == 0 and "NoControl" in rows[0]["statuses"]:
            # the recording starts in a room transition: the model starts at the first frame in control
            c = 0
            while c < len(rows) and "NoControl" in rows[c]["statuses"]:
                c += 1
            rows = rows[c + 1:]
        if k > 0:
            # entering from the previous room: the game gives control back one frame after the
            # last NoControl frame; the model's first frame in the room is the frame after that
            c = 0
            while c < len(rows) and "NoControl" in rows[c]["statuses"]:
                c += 1
            # a freeze when control comes back (Frozen(3) after the upward
            # transition into 1a_lvl_6, entered dashing): the game does not
            # update on those frames and the TAS waits them out. A frame was
            # frozen if the row before it shows Frozen (statuses are read
            # after the frame).
            while c + 1 < len(rows) and "Frozen" in rows[c]["statuses"]:
                c += 1
            rows = rows[c + 1:]
            proom, pbdir, proute, pexit = prev
            start = os.path.join(work, f"entry_{k}.h")
            next_entry(pbdir, proute, pexit, proom, room, start, f"entering {os.path.basename(room)}",
                       exit_h=os.path.join(work, f"exit_{k}.h"))
        if not rows:
            break
        ox, oy = room_origin(room)
        route = os.path.join(work, f"route_{k}.tas")
        open(route, "w").write("# the recording's inputs\n" + "".join(
            f"   1{',' + row_keys(r['inputs']) if row_keys(r['inputs']) else ''}\n" for r in rows))
        model, exit_frame = model_trace(room, route, start)
        n = len(model) if not exit_frame else exit_frame
        bad, died = None, None
        for f in range(n):
            g = dict(rows[f], x=rows[f]["x"] - ox, y=rows[f]["y"] - oy)
            m = model[f]
            if "Dead" in g["statuses"] or m.get("dead"):
                # the game zeroes her speed when she dies; the model stops where she died
                if "Dead" in g["statuses"] and m.get("dead") and same_position(m, g):
                    died = f + 1
                else:
                    bad = (f, m, g)
                break
            if exit_frame and f + 1 == exit_frame:
                if not (same_position(m, g) and "NoControl" in g["statuses"]):
                    bad = (f, m, g)
                break
            if not same(m, g):
                bad = (f, m, g)
                break
        frames_checked += (bad[0] if bad else n)
        where = os.path.basename(room)[:-4]
        if bad:
            f, m, g = bad
            report.append(f"{where}: first difference on frame {f + 1}: model ({m['x']:.6f}, {m['y']:.6f}) "
                          f"v=({m['vx']:.4f}, {m['vy']:.4f}) {m['state']}, game ({g['x']:.6f}, {g['y']:.6f}) "
                          f"v=({g['vx']:.4f}, {g['vy']:.4f}) {g['state']}")
            for q in range(max(0, f - 3), min(len(rows), len(model), f + 3)):   # context, zip mover included
                gq, mq = rows[q], model[q]
                gz = f" zip ({gq['zip'][0] - ox:.2f}, {gq['zip'][1] - oy:.2f})" if gq.get("zip") else ""
                mz = f" zip ({mq['zx']}, {mq['zy']}) t={mq['zt']}" if "zx" in mq else ""
                report.append(f"\n      frame {q + 1:3d} {gq['inputs'].strip():12s} game ({gq['x'] - ox:.4f}, {gq['y'] - oy:.4f}) "
                              f"v=({gq['vx']:.3f}, {gq['vy']:.3f}){gz} | model ({mq['x']:.4f}, {mq['y']:.4f}) "
                              f"v=({mq['vx']:.3f}, {mq['vy']:.3f}){mz}")
            ok = False
            break
        if died:
            report.append(f"{where}: {died - 1} frames identical, dies on frame {died} in both")
            break
        if exit_frame:
            report.append(f"{where}: {n} frames identical, leaves on frame {exit_frame} in both")
            prev = (room, model_bdir(room, start), route, exit_frame)
        else:
            report.append(f"{where}: {n} frames identical")
            break
    return f"{name}: " + "; ".join(report), ok


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ddir = sys.argv[1]
    rdir = sys.argv[2] if len(sys.argv) > 2 else VANILLA
    files = sorted(glob.glob(os.path.join(ddir, "celeste-sat-*.txt")) + glob.glob(os.path.join(ddir, "community-*.txt")))
    if not files:
        print(f"no recordings (celeste-sat-*.txt, community-*.txt) in {ddir}")
        return 0
    all_ok = True
    with tempfile.TemporaryDirectory() as work:
        for f in files:
            line, ok = check(f, rdir, work)
            print(("  " if ok else "!! " if ok is False else "-- ") + line)
            all_ok &= ok is not False
    print("MATCH" if all_ok else "MISMATCH")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
