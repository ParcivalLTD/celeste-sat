"""Where things are: the repository, its build directory, and the game's map files."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
ROOMS = os.path.join(ROOT, "rooms")
VANILLA = os.path.join(ROOMS, "vanilla")        # rooms exported from the game (mostly not in git)
GAME = os.path.join(ROOT, "game")               # put your own copies of the map files here (not in git)
EXE = ".exe" if sys.platform == "win32" else ""


def read_text(path, **kw):
    with open(path, **kw) as f:
        return f.read()


def write_text(path, text):
    with open(path, "w") as f:
        f.write(text)


def exe(bdir, name):
    """path of a program built into bdir (sim, beam, ...)"""
    return os.path.join(bdir, name + EXE)


def find_map(filename):
    """A Celeste map file (e.g. "1-ForsakenCity.bin") from your copy of the game.

    Looked for, in order: game/ in this repository, the repository root (where
    older checkouts kept it), and $CELESTE_DIR/Content/Maps. The map files are
    the game's content, so they are never committed: copy them from
    <Celeste>/Content/Maps or set CELESTE_DIR to the game's folder."""
    candidates = [os.path.join(GAME, filename), os.path.join(ROOT, filename)]
    if os.environ.get("CELESTE_DIR"):
        candidates.append(os.path.join(os.environ["CELESTE_DIR"], "Content", "Maps", filename))
    for c in candidates:
        if os.path.exists(c):
            return c
    sys.exit(f"{filename} not found. It is part of the game, so it is not in the repository: copy it from "
             f"<Celeste>/Content/Maps into {os.path.relpath(GAME, os.getcwd())}/, or set CELESTE_DIR to the "
             f"game's folder (looked in: {', '.join(candidates)})")
