#!/usr/bin/env python3
"""
make_room.py -- convert an ASCII room into room.h for the model.

    python3 tools/make_room.py rooms/ledge.txt build/ledge/room.h

The room format is described in celeste_sat/room.py (and docs/room-format.md);
what goes into room.h in celeste_sat/room_header.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celeste_sat import room_header  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    room_header.write(sys.argv[1], sys.argv[2])
