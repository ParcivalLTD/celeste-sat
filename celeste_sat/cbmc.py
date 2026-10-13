"""
Running CBMC on a harness and reading its answer.

Every harness (harness/solve.c, window.c, cross.c) asserts that something
can NOT happen ("she does not leave the room within N frames"). CBMC either
proves the assertion (VERIFICATION SUCCESSFUL: no such input sequence exists,
within the model) or gives a counterexample: the inputs of a route that does
it, read here from the trace of the harness's `inputs[]` array.
"""
import json
import re
import subprocess
import sys
import time

from .paths import ROOT

_INPUT = re.compile(r"inputs\[(\d+)l?\]\.(mx|my|jump|dash|grab|cdash)")


def command(*args):
    """cbmc with these arguments (on Windows CBMC needs --gcc to use gcc as its preprocessor)"""
    return ["cbmc"] + (["--gcc"] if sys.platform == "win32" else []) + list(args) + ["--trace", "--json-ui"]


def read_answer(text, n=None, where="CBMC output"):
    """CBMC's --json-ui output -> (False, None) proven / (True, frames) counterexample.

    frames: one (mx, my, jump, dash, grab, cdash) per entry of inputs[], n of
    them (default: up to the last one the trace assigns). Exits on output it
    cannot read."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        sys.exit(f"could not parse {where}:\n" + text[-2000:])
    for msg in data:
        for res in msg.get("result", []):
            if res["status"] == "SUCCESS":
                return False, None
            if res["status"] == "FAILURE":
                vals = {}
                for st in res.get("trace", []):
                    if st.get("stepType") != "assignment":
                        continue
                    m = _INPUT.fullmatch(st.get("lhs", ""))
                    if m:
                        d = st["value"]["data"]
                        vals[(int(m.group(1)), m.group(2))] = (d == "TRUE") if d in ("TRUE", "FALSE") else int(d)
                count = n if n is not None else 1 + max((i for i, _ in vals), default=-1)
                frames = [(vals.get((i, "mx"), 0), vals.get((i, "my"), 0), vals.get((i, "jump"), 0),
                           vals.get((i, "dash"), 0), vals.get((i, "grab"), False), vals.get((i, "cdash"), 0))
                          for i in range(count)]
                return True, frames
    sys.exit(f"unexpected {where}:\n" + text[-2000:])


def run(cmd, cwd, timeout, n=None):
    """run a CBMC command -> (found, frames, seconds); found is None on timeout"""
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, None, time.time() - t0
    dt = time.time() - t0
    try:
        json.loads(r.stdout)
    except json.JSONDecodeError:
        sys.exit("could not parse CBMC output:\n" + r.stdout[-2000:] + r.stderr[-2000:])
    found, frames = read_answer(r.stdout, n, where="CBMC output")
    return found, frames, dt


def leave_within(bdir, horizon, start_file, timeout):
    """harness/solve.c in a build directory: can she leave the room within `horizon`
    frames (from the spawn, or from the state in bdir/start_file)?
    -> (True, frames) a route / (False, None) proven impossible / (None, None) timeout, and seconds"""
    cmd = command("solve.c", "-I", ".", "-I", f"{ROOT}/model", f"-DNFRAMES={horizon}",
                  *([f'-DSTART_STATE_FILE="{start_file}"'] if start_file else []))
    return run(cmd, bdir, timeout, n=horizon)
