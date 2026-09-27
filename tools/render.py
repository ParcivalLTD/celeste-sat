#!/usr/bin/env python3
"""
render.py -- build a self-contained replay page from solved rooms.

    tools/render.py spec.json out.html

spec.json:
  {"rooms": [{"name": "ledge", "room": "rooms/ledge.txt", "build": "build/ledge",
              "lede": "...", "story": [{"f": 5, "t": "..."}], "notes": {"5": "..."},
              "log": [{"q": "...", "free": 13, "kind": "unsat", "a": "no", "time": "86 s"}],
              "status": "..."}]}
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def room_rows(path):
    return [l.rstrip("\n") for l in open(path) if l.strip() and not l.startswith(";")]


def main():
    spec = json.load(open(sys.argv[1]))
    rooms = []
    for r in spec["rooms"]:
        rows = room_rows(os.path.join(ROOT, r["room"]))
        trace = json.load(open(os.path.join(ROOT, r["build"], "trace.json")))
        tas = open(os.path.join(ROOT, r["build"], "best.tas")).read().strip()
        rooms.append(dict(name=r["name"], rows=rows, w=len(rows[0]), h=len(rows),
                          frames=trace["frames"], tas=tas, lede=r["lede"], story=r["story"],
                          notes={int(k): v for k, v in r.get("notes", {}).items()},
                          log=r["log"], status=r["status"]))
    html = open(os.path.join(ROOT, "tools", "replay_template.html")).read()
    html = html.replace("/*DATA*/null", json.dumps({"rooms": rooms}, separators=(",", ":")))
    open(sys.argv[2], "w").write(html)
    print(f"wrote {sys.argv[2]} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
