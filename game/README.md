# game/

Put your own copies of Celeste's map files here (they are part of the game,
so they are not in the repository and `.gitignore` keeps them out):

```
cp "<Celeste>/Content/Maps/1-ForsakenCity.bin" game/
cp "<Celeste>/Content/Maps/2-OldSite.bin" game/
```

`<Celeste>` is the game's folder, e.g. `~/.steam/steam/steamapps/common/Celeste`
or `C:\Program Files (x86)\Steam\steamapps\common\Celeste`. Instead of copying,
you can set `CELESTE_DIR` to that folder. The tools look in `game/`, then the
repository root, then `$CELESTE_DIR/Content/Maps` (`celeste_sat/paths.py`).

- `tests/chain_tas.py` (and everything that builds on it) needs `1-ForsakenCity.bin`.
- `tools/import_chapter2.py` needs `2-OldSite.bin`.
