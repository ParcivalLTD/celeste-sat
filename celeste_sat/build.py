"""
Building the model for one room, and running what was built.

Every room is its own build: room.h (celeste_sat/room_header.py) and the
timer tables (tools/gen_tables.c) go into a build directory together with
the simulator (sim/sim.c) and the beam search (search/beam.c) compiled
against them; the CBMC harnesses are compiled by CBMC from the same
directory.
"""
import os
import re
import shutil
import subprocess
import sys

from . import room_header
from .paths import ROOT, exe, read_text, write_text
from .tas import write_tas


def sh(cmd, **kw):
    """run a command (a list, or a string for the shell), capturing its output as text"""
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, **kw)


def carries_lift(state_file):
    """does a state header have a lift speed in its grace time (Actor.LiftSpeed)?"""
    text = read_text(state_file)
    m = re.search(r"\.liftGraceTimer = (-?\d+)", text)
    return bool(m and int(m.group(1)) > 0)


def build(room_path, bdir, start=None):
    """room.h, timer tables, sim and beam for a room in bdir; `start` is an
    optional state header (START_STATE) to begin from instead of the spawn
    (copied to bdir/entry.h)."""
    os.makedirs(bdir, exist_ok=True)
    try:
        room_header.write(room_path, f"{bdir}/room.h")
    except (AssertionError, OSError) as e:
        sys.exit(f"{room_path}: {e}")
    if start and carries_lift(start):
        with open(f"{bdir}/room.h", "a") as f:
            f.write("/* she enters with a lift speed still in its grace time */\n#define CARRIED_LIFT 1\n")
    gen = exe(bdir, "gen_tables")
    r = sh(["gcc", "-O0", "-I", f"{ROOT}/model", "-o", gen, f"{ROOT}/tools/gen_tables.c"])
    if r.returncode:
        sys.exit(r.stderr)
    write_text(f"{bdir}/tables.h", sh([gen]).stdout)
    flags = []
    if start:
        if os.path.abspath(start) != os.path.abspath(f"{bdir}/entry.h"):
            shutil.copy(start, f"{bdir}/entry.h")
        flags = ['-DSTART_STATE_FILE="entry.h"']
    for name, src, extra in (("sim", "sim/sim.c", []), ("beam", "search/beam.c", ["-fopenmp"])):
        r = sh(["gcc", "-O2", *extra, *flags, "-I", bdir, "-I", f"{ROOT}/model", "-o", exe(bdir, name), f"{ROOT}/{src}"])
        if r.returncode:
            sys.exit(r.stderr)
    shutil.copy(f"{ROOT}/harness/solve.c", f"{bdir}/solve.c")
    shutil.copy(f"{ROOT}/harness/input_rules.h", f"{bdir}/input_rules.h")


def run_sim(bdir, *args):
    """bdir/sim with these arguments -> CompletedProcess"""
    return sh([exe(bdir, "sim"), *args])


def exit_frame_of(output):
    """the frame `sim` reports she left the room on, or None"""
    m = re.search(r"EXIT at frame (\d+)", output)
    return int(m.group(1)) if m else None


def replay(bdir, tas, json_out=None):
    """the frame the route in `tas` leaves the room on (None: it does not)"""
    return exit_frame_of(run_sim(bdir, tas, *(["-j", json_out] if json_out else [])).stdout)


def replay_frames(bdir, frames, path, note="route"):
    """write `frames` to `path` and replay them -> exit frame or None"""
    write_tas(path, frames, [note])
    return replay(bdir, path)


def dump_state(bdir, tas, k, out):
    """the exact state after k frames of `tas` -> header `out` (sim -s)"""
    return run_sim(bdir, "-s", str(k), out, tas)
