"""
The community TAS (github.com/VampireFlower/CelesteTAS), at a fixed commit.

Its inputs have been played in the real game and finish the chapter, which
makes them the project's strongest check of the model (tests/chain_tas.py)
and the record to beat. They are not copied into this repository (the
repository they come from has no licence); they are downloaded on first use
and cached in build/cache/.

The commit is pinned so that results stay comparable. At this commit
1A.tas records "ChapterTime: 0:49.079(2887)" -- the in-game chapter timer,
which counts every frame from the level start, transitions and the 88-frame
intro included, not only the 2,275 frames of control.
"""
import os
import sys
import urllib.request

from .paths import BUILD, read_text

COMMIT = "098927faa0da3101bf9c2371f1e45d719c830821"
URL = f"https://raw.githubusercontent.com/VampireFlower/CelesteTAS/{COMMIT}/{{name}}"

# Chapter 1 (1A), the rooms the TAS goes through, in order
CH1_ORDER = ["lvl_1", "lvl_2", "lvl_3", "lvl_4", "lvl_3b", "lvl_5", "lvl_6", "lvl_6a", "lvl_6b", "lvl_6c", "lvl_7",
             "lvl_8", "lvl_8b", "lvl_9", "lvl_9b", "lvl_10a", "lvl_11", "lvl_12", "lvl_12a"]


def fetch(name="1A.tas", local=None):
    """the text of a community TAS file (`local`: use this copy instead)"""
    if local:
        return read_text(local, encoding="utf-8")
    cache = os.path.join(BUILD, "cache", "community", COMMIT[:12], name)
    if not os.path.exists(cache):
        try:
            data = urllib.request.urlopen(URL.format(name=name), timeout=30).read()
        except OSError as e:
            sys.exit(f"could not download the community {name} ({e}); pass a local copy with --tas")
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "wb") as f:
            f.write(data)
    return read_text(cache, encoding="utf-8", errors="replace")


def fetch_path(name="1A.tas", local=None):
    """like fetch, but the path of a file holding it"""
    if local:
        return local
    fetch(name)
    return os.path.join(BUILD, "cache", "community", COMMIT[:12], name)
