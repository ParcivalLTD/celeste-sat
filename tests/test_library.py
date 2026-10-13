#!/usr/bin/env python3
"""
test_library.py -- unit tests of the Python library (celeste_sat/), no build needed.

    python3 -m unittest discover -s tests -p "test_*.py"     (tools/run_tests.sh runs it)

The model itself is checked by tests/diff.sh (the two C builds against each
other) and tests/chain_tas.py (against the real game); these only pin down
the Python pieces the pipelines are built from.
"""
import glob
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat import cbmc, room_header  # noqa: E402
from celeste_sat.paths import ROOMS, ROOT, VANILLA  # noqa: E402
from celeste_sat.celeste_map import Element, solid_grid  # noqa: E402
from celeste_sat.recording import STATE_NAMES, parse_dump  # noqa: E402
from celeste_sat.room import parse, spike_box  # noqa: E402
from celeste_sat.state import read_state, write_state  # noqa: E402
from celeste_sat.tas import NOTHING, REPRESS, read_tas, sections, tas_keys, tas_lines, write_tas  # noqa: E402
from celeste_sat.transition import TRANSITION_GAP, carry_chaser_history, enter_room, exit_side, up_stop  # noqa: E402

TIMERS = {"VAR_JUMP_TIME": 12, "DASH_COOLDOWN": 12}   # stand-ins for tables.h


class TasFiles(unittest.TestCase):
    def roundtrip(self, frames):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.tas")
            write_tas(p, frames, ["a comment"])
            return read_tas(p)

    def test_every_saved_route_survives_a_round_trip(self):
        routes = glob.glob(os.path.join(ROOT, "results", "routes", "*.tas")) + \
            glob.glob(os.path.join(ROOT, "tests", "fixtures", "*.tas"))
        self.assertTrue(routes)
        for path in routes:
            frames = read_tas(path)
            self.assertEqual(self.roundtrip(frames), frames, path)

    def test_pressing_again_while_held_alternates_the_keys(self):
        # jump held, then pressed again with the other key, three frames in a row
        frames = [(0, 0, 1, 0, False, 0), (0, 0, REPRESS, 0, False, 0), (0, 0, REPRESS, 0, False, 0)]
        self.assertEqual(tas_keys(frames), [("J",), ("K",), ("J",)])
        self.assertEqual(self.roundtrip(frames), frames)

    def test_runs_are_merged(self):
        frames = [(1, 0, 0, 0, False, 0)] * 5 + [NOTHING] * 3 + [(-1, -1, 0, 1, True, 0)]
        self.assertEqual(tas_lines(frames), ["   5,R", "   3", "   1,L,U,X,G"])

    def test_sections_split_by_room_and_drop_the_transition_wait(self):
        text = "console load 1\n#Start\n  88\n\n#lvl_1\n   5,R,X\n  40\n# a comment\n#lvl_2\n   2,J\n#1SH0G\n   3,R\n  40\n"
        secs, order = sections(text)
        self.assertEqual(order, ["Start", "lvl_1", "lvl_2", "1SH0G"])
        self.assertEqual(secs["lvl_1"], ["5,R,X"])
        secs, order = sections(text, {"lvl_1", "lvl_2"})
        self.assertEqual(order, ["lvl_1", "lvl_2"])
        self.assertEqual(secs["lvl_2"], ["2,J", "3,R"])     # #1SH0G is not a room: it stays in lvl_2


class Rooms(unittest.TestCase):
    def test_demo_rooms_parse_and_render(self):
        for path in glob.glob(os.path.join(ROOMS, "*.txt")):
            r = parse(path)
            self.assertTrue(r.spawn, path)
            self.assertTrue(r.exits, path)
            h = room_header.render(r)
            self.assertIn(f"#define ROOM_W {r.width}", h)
            self.assertIn(f"#define NZIPMOVERS {len(r.zipmovers)}", h)

    def test_ledge(self):
        r = parse(os.path.join(ROOMS, "ledge.txt"))
        self.assertEqual((r.width_px, r.height_px), (r.width * 8, r.height * 8))
        self.assertTrue(any(goal for *_, goal in r.exits))

    def test_chapter2_rooms_have_an_origin(self):
        for path in glob.glob(os.path.join(VANILLA, "2a_*.txt")):
            self.assertIsNotNone(parse(path).origin, path)

    def test_spike_boxes_are_3px_strips(self):
        self.assertEqual(spike_box("up", 8, 16, 24), (8, 13, 32, 16))
        self.assertEqual(spike_box("left", 8, 16, 24), (5, 16, 8, 40))

    def test_zip_mover_returns_to_its_start(self):
        cycle = room_header.zip_cycle(112, 80, 184, 72)       # Chapter 1 lvl_4's
        self.assertEqual(cycle[0][:2], (112, 80))
        self.assertEqual(cycle[-1][:2], (112, 80))
        self.assertIn((184, 72), [e[:2] for e in cycle])


class Transition(unittest.TestCase):
    def state(self, **kw):
        st = dict(x=100, y=0, ducking=0, state=0, spdX=50.0, spdY=-200.0, varJumpSpeed=0.0, varJumpTimer=0,
                  varJumpLong=0, varJumpShort=0, dashCooldownTimer=0, autoJump=0, maxFall=160.0, coActive=0,
                  coWait=0, wallSpeedRetentionTimer=0, remX=0.25, remY=0.5)
        st.update(kw)
        return st

    def test_exit_side(self):
        self.assertEqual(exit_side(self.state(x=2, y=50), 320, 184), "left")
        self.assertEqual(exit_side(self.state(x=318, y=50), 320, 184), "right")
        self.assertEqual(exit_side(self.state(x=100, y=5), 320, 184), "up")
        self.assertEqual(exit_side(self.state(x=100, y=200), 320, 184), "down")

    def test_going_up(self):
        e = enter_room(self.state(), "up", (0, 0), (0, -184), 320, 184, TIMERS)
        self.assertEqual((e["spdX"], e["spdY"]), (0.0, -105.0))
        self.assertEqual(e["y"], up_stop(184))
        self.assertEqual((e["remX"], e["remY"]), (0.0, 0.0))
        self.assertEqual((e["dashes"], e["stamina"], e["autoJump"]), (1, 110.0, 1))

    def test_stop_point_depends_on_the_room_height(self):
        self.assertEqual(up_stop(184), 184 - 9)
        self.assertEqual(up_stop(288), 288 - 5)

    def test_chaser_history_runs_on_across_the_transition(self):
        n = 8
        st = dict(histX=list(range(n)), histY=[0] * n, chaserTimer=3)
        e = {}
        carry_chaser_history(e, st, 10, 0, 99, 7)
        self.assertEqual(e["chaserTimer"], n)
        self.assertEqual(len(e["histX"]), n)
        self.assertEqual(e["histX"][-1], 99)                  # the transition's frames stand at the entry
        if TRANSITION_GAP < n:
            self.assertEqual(e["histX"][n - 1 - TRANSITION_GAP], 2 + 10)

    def test_state_headers_round_trip(self):
        st = dict(x=12, y=-3, spdX=-105.5, remY=0.1, zipTimer=[0, 3, 0, 0])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.h")
            write_state(st, p, "test")
            self.assertEqual(read_state(p), st)


class Cbmc(unittest.TestCase):
    def test_proof(self):
        out = json.dumps([{"program": "CBMC"}, {"result": [{"property": "a", "status": "SUCCESS"}]}])
        self.assertEqual(cbmc.read_answer(out), (False, None))

    def test_counterexample(self):
        trace = [{"stepType": "assignment", "lhs": "inputs[1l].mx", "value": {"data": "1"}},
                 {"stepType": "assignment", "lhs": "inputs[1l].grab", "value": {"data": "TRUE"}},
                 {"stepType": "assignment", "lhs": "inputs[0l].jump", "value": {"data": "2"}},
                 {"stepType": "assignment", "lhs": "s.x", "value": {"data": "7"}}]
        out = json.dumps([{"result": [{"status": "FAILURE", "trace": trace}]}])
        found, frames = cbmc.read_answer(out)
        self.assertTrue(found)
        self.assertEqual(frames, [(0, 0, 2, 0, False, 0), (1, 0, 0, 0, True, 0)])
        self.assertEqual(len(cbmc.read_answer(out, n=4)[1]), 4)


def load_tool(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Splicing(unittest.TestCase):
    def setUp(self):
        self.sp = load_tool("splice_tas")

    def test_a_window_is_cut_out_of_its_route(self):
        orig = list(range(20))
        better = orig[:5] + ["a", "b"] + orig[9:]                 # frames 6..9 done in 2
        self.assertEqual(self.sp.window_segment(orig, 5, 3, better), ["a", "b"])
        with self.assertRaises(ValueError):
            self.sp.window_segment(orig, 5, 3, orig[:4] + ["a"] + orig[9:])

    def test_disjoint_windows_apply_together(self):
        orig = list(range(20))
        self.assertEqual(self.sp.apply_windows(orig, [(5, 3, ["a", "b"]), (12, 2, ["z"])]),
                         [0, 1, 2, 3, 4, "a", "b", 9, 10, 11, "z", 15, 16, 17, 18, 19])

    def test_the_best_set_of_windows(self):
        wins = [(0, 8, [1] * 7), (5, 8, [1] * 2), (10, 4, [1] * 3)]   # saves 2, 7, 2; the second overlaps both
        self.assertEqual(self.sp.best_disjoint(wins), [(5, 8, [1] * 2)])
        wins = [(0, 8, [1] * 4), (5, 8, [1] * 6), (10, 4, [1] * 1)]   # 5 + 4 beats 3
        self.assertEqual(self.sp.best_disjoint(wins), [(0, 8, [1] * 4), (10, 4, [1] * 1)])

    def test_replacing_a_room_with_its_own_inputs_changes_nothing(self):
        text = ("console load 1\n   1\n\n#Start\n  88\n\n#lvl_1\n   5,R,X\n   6,R,J\n  40\n\n"
                "#lvl_2\n   2,J\n  40\nChapterTime: 0:01.000(60)\n")
        frames = [(1, 0, 0, 1, False, 0)] * 5 + [(1, 0, 1, 0, False, 0)] * 6
        self.assertEqual(self.sp.replace_rooms(text, {"lvl_1": frames}), text.replace("ChapterTime: 0:01.000(60)\n", ""))
        out = self.sp.replace_rooms(text, {"lvl_1": frames[:5]})
        self.assertIn("#lvl_1\n   5,R,X\n  40\n", out)


class Chapter2Export(unittest.TestCase):
    def test_exit_fixes_apply_to_the_exported_line(self):
        m = load_tool("import_chapter2")
        self.assertEqual(m.apply_fixes("lvl_9", "a\n; exit down 256 576   (-> lvl_10)\nb"),
                         "a\n; exit down 488 512   (-> lvl_10)\nb")


class Recordings(unittest.TestCase):
    # two rows of data/recordings/celeste-sat-1a-6a118.txt (shortened): the
    # second has the extra LiftBoost column CelesteTAS adds before the room
    ROWS = ("Line\tInputs\tFrames\tTime\tPosition\tSpeed\tState\tStatuses\tRoom\tEntities\n"
            "131\t11/  13,R,X\t832\t0:11.713(689)\t1148.9, -763.0\t240.0, 0.0\tStDash\tJump(2)\t[5]\tWind: 0, 0\n"
            "131\t12/  13,R,X\t833\t0:11.730(690)\t1152.9, -763.0\t240.0, 0.0\tStDash\tJump(1)\t"
            "LiftBoost(10): 0.0, -58.6\t[5]\tWind: 0, 0\n")

    def test_an_extra_column_before_the_room(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dump.txt")
            with open(path, "w") as f:
                f.write(self.ROWS)
            rows = parse_dump(path)
        self.assertEqual([r["room"] for r in rows], ["[5]", "[5]"])
        self.assertEqual(rows[1]["statuses"], "Jump(1) LiftBoost(10): 0.0, -58.6")
        self.assertEqual(rows[1]["entities"], "Wind: 0, 0")

    def test_every_model_state_has_the_game_name(self):
        text = open(os.path.join(ROOT, "model", "celeste.h")).read()
        for name, value in re.findall(r"#define (ST_\w+)\s+(\d+)", text):
            self.assertIn(int(value), STATE_NAMES, name)


def _map(levels, fillers=()):
    """a map tree like read_map's: levels as (name, x, y, rows), fillers in tiles"""
    root, lv, fl = Element("Map"), Element("levels"), Element("Filler")
    for name, x, y, rows in levels:
        e, s = Element("level"), Element("solids")
        e.attrs = {"name": name, "x": x, "y": y, "width": len(rows[0]) * 8, "height": len(rows) * 8}
        s.attrs = {"innerText": "\n".join(r.replace("#", "1").replace(".", "0") for r in rows)}
        e.children = [s]
        lv.children.append(e)
    for x, y, w, h in fillers:
        f = Element("rect")
        f.attrs = {"x": x, "y": y, "w": w, "h": h}
        fl.children.append(f)
    root.children = [fl, lv]
    return root


class TilesOutsideRooms(unittest.TestCase):
    # LevelLoader's fill (celeste_map.solid_grid): a 4 x 3 room at tile (10, 10)
    # far from the map's edge (a second room and a filler stretch the bounds)
    ROOM = ["#..#", "#...", "####"]

    def grid(self, fillers=()):
        return solid_grid(_map([("a", 80, 80, self.ROOM), ("far", 0, 0, ["."]), ("far2", 200, 200, ["."])], fillers))

    def test_solid_top_tiles_extend_three_up(self):
        g = self.grid()
        self.assertTrue({(10, 9), (10, 8), (10, 7), (13, 7)} <= g)
        self.assertNotIn((10, 6), g)

    def test_air_top_tiles_keep_the_column_above_empty(self):
        g = self.grid()
        self.assertFalse({(11, 9), (12, 9), (11, 7)} & g)

    def test_edge_columns_extend_three_sideways(self):
        g = self.grid()
        self.assertTrue({(9, 12), (8, 12), (7, 12), (9, 10)} <= g)
        self.assertNotIn((6, 12), g)
        self.assertNotIn((14, 11), g)                   # right edge of row 1 is air

    def test_a_filler_is_solid(self):
        g = self.grid(fillers=[(20, 20, 2, 2)])
        self.assertTrue({(20, 20), (21, 21)} <= g)


if __name__ == "__main__":
    unittest.main()
