"""
The model's state as a C header.

`sim -s K out.h route.tas` writes Madeline's exact state after K frames as a
designated initializer (`static const State START_STATE = { .x = ..., };`,
floats in hex). The simulator, the beam search and the CBMC harnesses can
start from such a header (-DSTART_STATE_FILE), which is how a run continues
in the next room and how a SAT query starts in the middle of a route.
"""
import os
import re

from .paths import read_text, write_text

# fields of State that are floats (model/celeste.h); the rest are integers or arrays of them
FLOAT_FIELDS = {"remX", "remY", "spdX", "spdY", "beforeDashSpdX", "beforeDashSpdY", "varJumpSpeed",
                "wallSpeedRetained", "maxFall", "stamina", "liftSpeedX", "liftSpeedY", "liftLastX", "liftLastY"}


def read_state(path):
    """the fields of a START_STATE header -> {name: int | float | [int]}"""
    st = {}
    for m in re.finditer(r"\.(\w+)\s*=\s*(\{[^}]*\}|[^,\n]+),", read_text(path)):
        name, v = m.group(1), m.group(2).strip()
        if v.startswith("{"):                       # an array (zipTimer, histX, ...)
            st[name] = [int(x) for x in v.strip("{}").split(",") if x.strip()]
        else:
            st[name] = float.fromhex(v.rstrip("f")) if name in FLOAT_FIELDS else int(v)
    return st


def write_state(st, path, note):
    """a START_STATE header (START_FRAMES 0) from read_state's dict"""
    lines = [f"/* {note} */", "#define START_FRAMES 0", "static const State START_STATE = {"]
    for k, v in st.items():
        if isinstance(v, list):
            lines.append(f"    .{k} = {{{', '.join(str(int(x)) for x in v)}}},")
        else:
            lines.append(f"    .{k} = {float(v).hex()}f," if k in FLOAT_FIELDS else f"    .{k} = {int(v)},")
    lines.append("};")
    write_text(path, "\n".join(lines) + "\n")


def tables(bdir):
    """the timer lengths in frames from a build's tables.h (tools/gen_tables.c): {"VAR_JUMP_TIME": 12, ...}"""
    k = {}
    for line in read_text(os.path.join(bdir, "tables.h")).splitlines():
        m = re.match(r"#define K_(\w+) (\d+)", line)
        if m:
            k[m.group(1)] = int(m.group(2))
    return k
