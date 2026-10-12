"""
celeste_sat -- the Python side of celeste-sat.

The model itself is C (model/); this package holds everything the pipelines
share: reading and writing TAS files, parsing rooms, building the simulator
and beam search for a room, reading the states the simulator dumps, the room
transition, running CBMC, and reading Celeste's map files and CelesteTAS
recordings. The scripts in tools/, tests/ and experiments/ are thin command
lines on top of it.

    tas          CelesteTAS-style input files (read, write, split by room)
    room         the ASCII room format -> Room
    room_header  Room -> room.h for the C model (zip mover paths etc.)
    build        build the model for a room; replay a route; dump a state
    state        the START_STATE headers `sim -s` writes
    transition   the room transition (what the game does between rooms)
    cbmc         run CBMC and read its counterexample
    celeste_map  Celeste's map files (Content/Maps/*.bin)
    recording    CelesteTAS ExportGameInfo recordings vs the model
    community    the community TAS (VampireFlower/CelesteTAS), fetched on demand
    paths        where things are (repo, build dir, the game's map files)
"""
