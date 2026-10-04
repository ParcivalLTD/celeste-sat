#!/usr/bin/env python3
"""
entity_census.py -- which entities are still unmodelled, and where.

    python3 tools/entity_census.py "<Celeste>/Content/Maps"            # every map
    python3 tools/entity_census.py 1-ForsakenCity.bin --tas recordings/1A.tas
    python3 tools/entity_census.py "<Celeste>/Content/Maps" --json census.json

The verdict comes from tools/import_map.py itself: every room is exported and
the census reads the "; NOT MODELLED (ignored)" and "; no effect on movement"
lines of the result. So this cannot drift from what the exporter actually
supports -- add an entity there and it disappears from here.

With --tas, the rooms a community TAS actually visits are marked on-route.
An entity in an on-route room blocks that chapter; one only in side rooms
(cassette, B-side gems, collectables) does not, and that distinction is the
whole point of the ranking: ROADMAP.md "Phase 1" works down this list.

Exit status is 0 even when entities are missing -- it is a report, not a test.
"""
import argparse, json, os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from import_map import entities, export, read_map, rooms  # noqa: E402

NOT_MODELLED = re.compile(r"^; NOT MODELLED \(ignored\): (.*)$", re.M)
COSMETIC_LINE = re.compile(r"^; no effect on movement: (.*)$", re.M)


def route_rooms(tas_path, names):
    """the rooms a CelesteTAS file visits, in order (its #room labels)"""
    from chain_tas import sections
    return sections(open(tas_path).read(), names)[1]


def census_map(path, tas=None):
    """-> (package, [per-room dict])"""
    package, root = read_map(path)
    lv = rooms(root)
    names = {l.attrs["name"] for l in lv}
    on_route = set(route_rooms(tas, names)) if tas else None

    out = []
    for level in lv:
        name = level.attrs["name"]
        counts = defaultdict(int)
        for e in entities(level):
            counts[e.name] += 1
        try:
            text = export(package, level, lv)
        except Exception as exc:                  # a room the exporter cannot read at all
            out.append(dict(room=name, error=f"{type(exc).__name__}: {exc}",
                            missing=sorted(counts), counts=dict(counts),
                            on_route=on_route is not None and name in on_route))
            continue
        m = NOT_MODELLED.search(text)
        missing = [s.strip() for s in m.group(1).split(",")] if m else []
        c = COSMETIC_LINE.search(text)
        cosmetic = [s.strip() for s in c.group(1).split(",")] if c else []
        out.append(dict(room=name, missing=missing, cosmetic=cosmetic,
                        counts={k: counts[k] for k in missing},
                        on_route=on_route is not None and name in on_route,
                        routed=on_route is not None))
    return package, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("maps", nargs="+", help="map files, or a directory of them (Content/Maps)")
    ap.add_argument("--tas", help="a community TAS file: mark the rooms it visits as on-route "
                                  "(only meaningful with a single map)")
    ap.add_argument("--json", help="also write the full per-room census here")
    a = ap.parse_args()

    paths = []
    for m in a.maps:
        if os.path.isdir(m):
            paths += [os.path.join(m, f) for f in sorted(os.listdir(m)) if f.endswith(".bin")]
        else:
            paths.append(m)
    if not paths:
        sys.exit("no .bin map files found")
    if a.tas and len(paths) > 1:
        sys.exit("--tas marks the route of one map; give a single map file with it")

    # entity -> rooms it appears in, and how many of those are on the route
    where = defaultdict(list)
    total, clean, routed_total, routed_clean, report = 0, 0, 0, 0, []
    for path in paths:
        package, per_room = census_map(path, a.tas)
        report.append(dict(map=package, file=os.path.basename(path), rooms=per_room))
        for r in per_room:
            total += 1
            if r["on_route"]:
                routed_total += 1
            if not r["missing"] and "error" not in r:
                clean += 1
                if r["on_route"]:
                    routed_clean += 1
            for name in r["missing"]:
                where[name].append((package, r["room"], r["counts"].get(name, 1), r["on_route"]))
        miss = sum(1 for r in per_room if r["missing"] or "error" in r)
        print(f"{package:28s} {len(per_room):3d} rooms, {len(per_room) - miss:3d} fully modelled, "
              f"{miss:3d} with something missing")

    print(f"\n{clean}/{total} rooms fully modelled"
          + (f"; on the TAS route: {routed_clean}/{routed_total}" if a.tas else ""))

    if not where:
        print("\nnothing unmodelled. Every room of every map given is covered.")
    else:
        print(f"\n{len(where)} unmodelled entities, most widespread first"
              + (" (* = in a room the TAS route visits)" if a.tas else "") + ":\n")
        print(f"  {'entity':28s} {'rooms':>5s} {'total':>6s}  {'maps':>4s}  where")
        ranked = sorted(where.items(), key=lambda kv: (-sum(1 for w in kv[1] if w[3]), -len(kv[1]), kv[0]))
        for name, ws in ranked:
            maps = sorted({w[0] for w in ws})
            n_routed = sum(1 for w in ws if w[3])
            star = "*" if n_routed else " "
            shown = ", ".join(f"{w[0].split('-')[0]}:{w[1]}" for w in ws[:4])
            if len(ws) > 4:
                shown += f", +{len(ws) - 4} more"
            print(f" {star}{name:28s} {len(ws):5d} {sum(w[2] for w in ws):6d}  {len(maps):4d}  {shown}")
        if a.tas:
            blocking = [n for n, ws in ranked if any(w[3] for w in ws)]
            print(f"\non the route, so blocking: {', '.join(blocking) if blocking else 'nothing'}")

    if a.json:
        json.dump(report, open(a.json, "w"), indent=1)
        print(f"\nfull per-room census: {a.json}")


if __name__ == "__main__":
    main()
