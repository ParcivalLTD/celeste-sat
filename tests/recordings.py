#!/usr/bin/env python3
"""
recordings.py -- check the model against recordings made in the real game.

CelesteTAS's ExportGameInfo writes, for every frame it plays, the input of
that frame and Madeline's exact position (pixel + subpixel), speed and
state. This replays each recording's own inputs through the model and
compares every frame, room after room: when she leaves a room, the next one
starts from the state the model gives her on entering it (tools/chapter.py),
at the first frame the game gives control back.

    python3 tests/recordings.py DIR [rooms/vanilla]

DIR is where CelesteTAS wrote the recordings (the Celeste folder, e.g.
/mnt/r/SteamLibrary/steamapps/common/Celeste in WSL); every
celeste-sat-*.txt and community-*.txt there is checked. The files in
results/celestetas/ record to such names. A recording that starts in the
middle of the chapter (the community TAS from its #lvl_3, say: name it
community-*.txt) starts from the state the community TAS enters that room
with, which tests/community_tas.py computes; run that first.
"""
import glob, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from celestetas import model_trace, parse_dump, room_origin, row_keys, same  # noqa: E402
from chapter import enter_room, exit_side, origin_of, read_state, tables, write_state  # noqa: E402
from make_room import parse  # noqa: E402
from solve import build  # noqa: E402

TOL = 2e-3


def room_file(rdir, tag):
    """"[3]" -> rooms/vanilla/1a_lvl_3.txt"""
    m = re.fullmatch(r"\[(\w+)\]", tag)
    return os.path.join(rdir, f"1a_lvl_{m.group(1)}.txt") if m else None


def check(path, rdir, work):
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
            start = os.path.join(ROOT, "build", "community_tas", f"entry_lvl_{m.group(1)}"
                                 + ("_edit" if "-edit" in name else "") + ".h")
            chained = os.path.join(ROOT, "build", "chain_tas", f"entry_lvl_{m.group(1)}.h")
            if not os.path.exists(start) and "-edit" not in name and os.path.exists(chained):
                start = chained                  # entered as tests/chain_tas.py plays the TAS up to there
            if not os.path.exists(start):
                return f"{name}: needs {start} (run tests/community_tas.py first)", None
    prev = None                                  # (room file, build dir, route file, exit frame)
    for k, (tag, a, b) in enumerate(segs):
        room = room_file(rdir, tag)
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
            rows = rows[c + 1:]
            proom, pbdir, proute, pexit = prev
            exit_h = os.path.join(work, f"exit_{k}.h")
            subprocess.run([os.path.join(pbdir, "sim"), "-s", str(pexit), exit_h, proute], capture_output=True)
            st = read_state(exit_h)
            r0, r1 = parse(proom)[0], parse(room)[0]
            e = enter_room(st, exit_side(st, len(r0[0]) * 8, len(r0) * 8), origin_of(proom), origin_of(room),
                           len(r1[0]) * 8, len(r1) * 8, tables(pbdir))
            start = os.path.join(work, f"entry_{k}.h")
            write_state(e, start, f"entering {os.path.basename(room)}")
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
                if "Dead" in g["statuses"] and m.get("dead") and abs(m["x"] - g["x"]) <= TOL and abs(m["y"] - g["y"]) <= TOL:
                    died = f + 1
                else:
                    bad = (f, m, g)
                break
            if exit_frame and f + 1 == exit_frame:
                if not (abs(m["x"] - g["x"]) <= TOL and abs(m["y"] - g["y"]) <= TOL and "NoControl" in g["statuses"]):
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
            bdir = os.path.join(ROOT, "build", f"check_{os.path.basename(room)[:-4]}" + ("_entry" if start else ""))
            prev = (room, bdir, route, exit_frame)
        else:
            report.append(f"{where}: {n} frames identical")
            break
    return f"{name}: " + "; ".join(report), ok


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ddir = sys.argv[1]
    rdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "rooms", "vanilla")
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
