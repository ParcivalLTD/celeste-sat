"""
CelesteTAS-style input files.

A line is "  12,R,J": a frame count, then the keys held on those frames.
L R U D are the directions, J/K the two jump keys, X/C the two dash keys, Z/V
the two crouch dash keys, G/H grab. A button is pressed on any frame where one
of its keys goes down, so pressing the other key presses it again without a
release (model/celeste.h, Input). Lines starting with '#' are comments.

In Python a route is a list of frames, each a tuple
(mx, my, jump, dash, grab, cdash) with the values of the C Input struct:
mx, my in {-1, 0, 1}; jump, dash, cdash in {0, 1, REPRESS}; grab a bool.
sim/tas_io.h is the C twin of this module and must agree with it.
"""
import re
import sys

from .paths import read_text, write_text

REPRESS = 2                       # held, and pressed again with the other key (BTN_REPRESS)
NOTHING = (0, 0, 0, 0, False, 0)  # a frame with no input


def _button(now, prev):
    """button value (0, 1 or REPRESS) from its two keys now and on the previous frame"""
    held = now[0] or now[1]
    was = prev[0] or prev[1]
    press = (now[0] and not prev[0]) or (now[1] and not prev[1])
    return 0 if not held else (REPRESS if was and press else 1)


def read_tas(path):
    """the frames of a TAS file (see the module docstring)"""
    frames, pj, pd, pz = [], (False, False), (False, False), (False, False)
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip().upper() for p in line.split(",")]
        if not parts[0].isdigit():
            continue
        n = int(parts[0])
        keys = set(parts[1:])
        unknown = keys - set("LRUDJKXCZVGH")
        if unknown:
            sys.exit(f"{path}: input {sorted(unknown)} is not modelled (line: {line})")
        j, d, z = ("J" in keys, "K" in keys), ("X" in keys, "C" in keys), ("Z" in keys, "V" in keys)
        mx = -1 if "L" in keys else 1 if "R" in keys else 0
        my = -1 if "U" in keys else 1 if "D" in keys else 0
        g = "G" in keys or "H" in keys
        for _ in range(n):
            frames.append((mx, my, _button(j, pj), _button(d, pd), g, _button(z, pz)))
            pj, pd, pz = j, d, z
    return frames


def tas_keys(frames):
    """the keys of each frame: a fresh press uses J (X, Z), a press while the
    button is held switches to the other key"""
    out, jk, dk, zk = [], None, None, None

    def nxt(b, cur, keys):
        if not b:
            return None
        if cur is None:
            return keys[0]
        return (keys[1] if cur == keys[0] else keys[0]) if b == REPRESS else cur

    for mx, my, jmp, dash, grab, cdash in frames:
        jk, dk, zk = nxt(jmp, jk, "JK"), nxt(dash, dk, "XC"), nxt(cdash, zk, "ZV")
        k = []
        if mx < 0: k.append("L")
        if mx > 0: k.append("R")
        if my < 0: k.append("U")
        if my > 0: k.append("D")
        if jk: k.append(jk)
        if dk: k.append(dk)
        if zk: k.append(zk)
        if grab: k.append("G")
        out.append(tuple(k))
    return out


def tas_lines(frames):
    """the input lines of a route (runs of identical frames merged), without comments"""
    keys = tas_keys(frames)
    out, i = [], 0
    while i < len(keys):
        j = i
        while j < len(keys) and keys[j] == keys[i]:
            j += 1
        out.append(",".join([f"{j - i:4d}", *keys[i]]))
        i = j
    return out


def write_tas(path, frames, header):
    """a TAS file: one '# ' comment line per header line, then the inputs"""
    out = [f"# {h}" for h in header] + tas_lines(frames)
    write_text(path, "\n".join(out) + "\n")


_LABEL = re.compile(r"#(\S+)")        # "#lvl_1" is a label (CelesteTAS); "# text" is a comment


def sections(text, rooms=None):
    """Split a CelesteTAS file (e.g. the community 1A.tas) by its #labels.

    -> ({label: [input lines]}, [labels in order]). With `rooms`, only labels
    in that set start a section; others (like #1SH0G) stay inside the room
    they are in. Each section's last line is dropped if it is a bare frame
    count ("  40": waiting out the room transition)."""
    out, order, cur = {}, [], None
    for line in text.splitlines():
        s = line.strip()
        m = _LABEL.match(s)
        if m and (rooms is None or m.group(1) in rooms):
            cur = m.group(1)
            out[cur] = []
            order.append(cur)
        elif cur and re.match(r"\d+", s):
            out[cur].append(s)
    for lines in out.values():
        if lines and re.fullmatch(r"\d+", lines[-1]):
            lines.pop()          # one: a route may itself end with idle frames before the wait
    return out, order
