# Rooms

Every room is a text file, one character per 8x8 tile, with directives for
the exact spawn, the exits and every entity. The demo rooms in `rooms/` are
written by hand; the rooms of the game are exported from its map files.
`celeste_sat/room.py` parses the format (its docstring is the reference) and
`celeste_sat/room_header.py` turns a room into the `room.h` the model is
compiled with (`python3 tools/make_room.py ROOM.txt room.h`).

## Room format

One character per 8×8 tile: `#` solid, `.` air, `S` spawn, spikes as
`^` `v` `<` `>` (the direction they point; the tile is air and the spikes sit
on the neighbouring solid face) and `-` for a jump-through platform along the
top of the tile. Directives:

```
; origin 896 -1256       world position of the top-left corner (needed to carry her into the next room)
; spawn 19 144           exact spawn in pixels (overrides S); "; spawn 120 168 -1": facing left
; exit up 240 560        the goal: a neighbouring room above, covering x in [240, 560)
; leave down -240 80     a neighbouring room that is not the goal (going there = failing)
; spikes left 272 80 16  spikes in the game's entity coordinates
; jumpthru 8 160 40      a jump-through platform, top edge at y = 160, x in [8, 48)
; spring 120 144         a floor spring, base centre at (120, 144)
; refill 152 72          a dash refill centred at (152, 72)
; zipmover 112 80 24 16 184 72   a zip mover: top-left (112, 80), 24 x 16, moving to (184, 72)
; fallingblock 152 160 32 24 1   a falling block: top-left (152, 160), 32 x 24; 1 = climbing it sets it off too
; crumble 232 152 24     a crumble block: top-left (232, 152), 24 x 8
; dashblock 304 240 24 32 1      a dash block, 24 x 32; 1 = a dash breaks it
; barrier 320 128 16 24  an invisible barrier, 16 x 24 (a solid that is never drawn)
; dreamblock 56 16 160 32        a dream block (Chapter 2)
; switchgate 48 0 24 16 48 64    a switch gate, moving to (48, 64) once every touch switch is on
; touchswitch 200 120    a touch switch centred at (200, 120)
; chaser 93              a Badeline chaser, 93 frames behind her (one line per chaser)
```

Without an `exit` line the whole right edge is the exit. Spikes and springs
act in the order they are listed, as in the game. Limits (from the sizes in
`State`): 4 zip movers and switch gates together, 4 falling blocks, 8 crumble
blocks, 8 dash blocks, 8 dream blocks, 8 barriers, 8 touch switches, 8
refills, rooms up to 128 tiles tall.

## Rooms from the game

`tools/import_map.py` reads the map files of your own copy of the game
(`Content/Maps/*.bin`, Celeste's BinaryPacker format; copy them into `game/`,
see [game/README.md](../game/README.md)) and exports a room with its tiles,
spawn, exits (one per neighbouring room) and every modelled entity:

```
python3 tools/import_map.py game/1-ForsakenCity.bin          # list rooms
python3 tools/import_map.py game/1-ForsakenCity.bin lvl_1 --to lvl_2 -o rooms/vanilla/1a_lvl_1.txt
python3 tools/solve.py rooms/vanilla/1a_lvl_1.txt --polish --from-frame 85
```

`tests/chain_tas.py` exports all of Chapter 1's rooms on the TAS's route as it
goes, and `tools/import_chapter2.py` all of Chapter 2's. Extracted rooms stay
out of git (`rooms/vanilla/` is ignored, except Chapter 2's for now). Other
entities are listed in the export as "NOT MODELLED"; `tools/entity_census.py`
counts them over whole maps. `--to lvl_3` makes the room above the goal;
going back down to `lvl_1` then counts as failing.

`tools/import_chapter2.py` also narrows two exits by hand (`EXIT_FIXES`): the
export makes the whole edge shared with the next room an exit, and in
`2a_lvl_9` and `2a_lvl_10` only part of it leads anywhere.
