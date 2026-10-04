#!/usr/bin/env python3
"""Random enclosed room for fuzzing: blocks, spikes, and one or two exits
(right edge as before, or left/up/down)."""
import random, sys
seed = int(sys.argv[1]); random.seed(seed)
W, H = random.randint(12, 28), random.randint(8, 18)
g = [['.'] * W for _ in range(H)]
for x in range(W): g[0][x] = g[H-1][x] = '#'
for y in range(H): g[y][0] = g[y][W-1] = '#'
for _ in range(random.randint(3, W * H // 8)):          # random blocks
    bw, bh = random.randint(1, 4), random.randint(1, 3)
    bx, by = random.randint(1, W - 2), random.randint(1, H - 2)
    for y in range(by, min(by + bh, H - 1)):
        for x in range(bx, min(bx + bw, W - 1)):
            g[y][x] = '#'

exits = []
sides = ["right"] if seed % 3 == 0 else random.sample(["right", "left", "up", "down"], random.randint(1, 2))
for k, side in enumerate(sides):
    kind = "leave" if k > 0 and random.random() < 0.5 else "exit"   # sometimes the second room is not the goal
    if side in ("right", "left"):                       # opening 2-3 tiles tall
        ey = random.randint(2, H - 4)
        x = W - 1 if side == "right" else 0
        for y in range(ey, min(ey + random.randint(2, 3), H - 1)): g[y][x] = '.'
        a = 0 if random.random() < 0.5 else ey * 8      # neighbour: whole edge or from the opening down
        exits.append(f"; {kind} {side} {a} {H * 8}")
    else:                                               # opening 2-4 tiles wide
        ex = random.randint(2, W - 5)
        y = 0 if side == "up" else H - 1
        for x in range(ex, min(ex + random.randint(2, 4), W - 1)): g[y][x] = '.'
        # the neighbour covers the whole opening, or only its right part (the rest is a dead end)
        exits.append(f"; {kind} {side} {ex * 8 + 8 * random.randint(-1, 1)} {W * 8}")
if "up" not in sides and random.random() < 0.3:       # sometimes a skylight with no room above
    sx = random.randint(2, W - 5)
    for x in range(sx, sx + random.randint(2, 3)): g[0][x] = '.'
if "down" not in sides and random.random() < 0.3:     # sometimes a pit (death)
    px = random.randint(3, W - 4); g[H-1][px] = '.'

spawn_col = 1 if "left" not in sides else W - 2
for y in (H - 2, H - 3, H - 4): g[y][spawn_col] = '.'   # spawn column clear
g[H-1][spawn_col] = '#'

# spikes on random free faces (tile-aligned, drawn as ^ v < >)
for _ in range(random.randint(0, W * H // 20)):
    x, y = random.randint(1, W - 2), random.randint(1, H - 2)
    if g[y][x] != '.' or x == spawn_col:
        continue
    faces = []
    if g[y + 1][x] == '#': faces.append('^')
    if g[y - 1][x] == '#': faces.append('v')
    if g[y][x + 1] == '#': faces.append('<')
    if g[y][x - 1] == '#': faces.append('>')
    if faces:
        g[y][x] = random.choice(faces)
g[H-2][spawn_col] = 'S'

# jump-through platforms (drawn as -) and floor springs
for _ in range(random.randint(0, 3)):
    y, x = random.randint(2, H - 3), random.randint(1, W - 3)
    for dx in range(random.randint(1, 4)):
        if x + dx < W - 1 and g[y][x + dx] == '.' and x + dx != spawn_col:
            g[y][x + dx] = '-'
springs = []
for _ in range(random.randint(0, 2)):
    x, y = random.randint(2, W - 3), random.randint(1, H - 2)
    if g[y][x] == '.' and g[y][x - 1] == '.' and g[y][x + 1] == '.' and g[y + 1][x] == '#' and x != spawn_col:
        springs.append(f"; spring {x * 8 + random.choice([0, 4])} {(y + 1) * 8}")

extra = []
for _ in range(random.randint(0, 2)):                   # a few spikes off the tile grid
    d = random.choice(["up", "down", "left", "right"])
    extra.append(f"; spikes {d} {random.randint(8, W * 8 - 16)} {random.randint(8, H * 8 - 16)} {random.choice([8, 12, 16])}")

# zip movers (every other room; drawn last so the other rooms stay as they were)
zips = []
if seed % 2 == 0:
    for _ in range(random.randint(1, 2)):
        for _try in range(60):
            zw, zh = random.randint(2, 4), random.randint(1, 2)          # tiles
            zx, zy = random.randint(1, W - 1 - zw), random.randint(2, H - 1 - zh)
            cells = [(x, y) for x in range(zx, zx + zw) for y in range(zy, zy + zh)]
            if any(g[y][x] != '.' for x, y in cells) or any(abs(x - spawn_col) <= 1 and y >= H - 5 for x, y in cells):
                continue
            tx = min(max(zx * 8 + random.randint(-80, 80), 8), W * 8 - 8 - zw * 8)
            ty = min(max(zy * 8 + random.randint(-48, 32), 8), H * 8 - 8 - zh * 8)
            zips.append(f"; zipmover {zx * 8} {zy * 8} {zw * 8} {zh * 8} {tx} {ty}")
            for x, y in cells:
                g[y][x] = 'z'                                            # keep later zip movers apart
            break
    g = [[c if c != 'z' else '.' for c in r] for r in g]

# refills (every third room)
refills = []
if seed % 3 == 1:
    for _ in range(random.randint(1, 2)):
        x, y = random.randint(2, W - 3), random.randint(2, H - 3)
        if g[y][x] == '.' and abs(x - spawn_col) > 1:
            refills.append(f"; refill {x * 8 + random.choice([0, 4])} {y * 8 + random.choice([0, 4])}")

# falling blocks (odd rooms, which have no zip movers), sometimes with spikes on
# them; each in its own columns, so none falls onto another
falls = []
if seed % 2 == 1:
    used = set()
    for _ in range(random.randint(1, 2)):
        for _try in range(60):
            fw, fh = random.randint(1, 4), random.randint(1, 3)          # tiles
            fx, fy = random.randint(1, W - 1 - fw), random.randint(1, H - 2 - fh)
            cells = [(x, y) for x in range(fx, fx + fw) for y in range(fy, fy + fh)]
            if any(g[y][x] != '.' for x, y in cells) or any(abs(x - spawn_col) <= 1 for x, _ in cells) \
                    or any(x in used for x, _ in cells):
                continue
            falls.append(f"; fallingblock {fx * 8} {fy * 8} {fw * 8} {fh * 8} {random.randint(0, 1)}")
            used |= {x for x, _ in cells} | {fx - 1, fx + fw}
            r = random.random()                                          # spikes riding on it
            if r < 0.25:
                falls.append(f"; spikes up {fx * 8} {fy * 8} {fw * 8}")
            elif r < 0.4:
                falls.append(f"; spikes down {fx * 8} {(fy + fh) * 8} {fw * 8}")
            elif r < 0.55:
                falls.append(f"; spikes {random.choice(['left', 'right'])} "
                             f"{fx * 8 if random.random() < 0.5 else (fx + fw) * 8} {fy * 8} {fh * 8}")
            break

# crumble blocks (every third room): 8 px tall platforms in the air, out of
# the falling blocks' columns
crumbles = []
if seed % 3 == 2:
    fall_cols = used if seed % 2 == 1 else set()
    for _ in range(random.randint(1, 3)):
        cw = random.randint(1, 4)
        cx, cy = random.randint(1, W - 1 - cw), random.randint(2, H - 3)
        cells = [(x, cy) for x in range(cx, cx + cw)]
        if all(g[y][x] == '.' for x, y in cells) and all(abs(x - spawn_col) > 1 for x, _ in cells) \
                and not any(x in fall_cols for x, _ in cells):
            crumbles.append(f"; crumble {cx * 8} {cy * 8} {cw * 8}")
            for x, y in cells:
                g[y][x] = 'c'
    g = [[ch if ch != 'c' else '.' for ch in r] for r in g]

# dash blocks (every fifth room): boxes in the air or against a wall, out of
# the falling blocks' columns and away from the crumble blocks
dashblocks = []
if seed % 5 == 3:
    fall_cols = used if seed % 2 == 1 else set()
    want = random.randint(1, 3)
    for _ in range(40):
        if len(dashblocks) == want:
            break
        bw, bh = random.randint(1, 3), random.randint(1, 4)
        bx, by = random.randint(1, W - 1 - bw), random.randint(1, H - 1 - bh)
        cells = [(x, y) for x in range(bx, bx + bw) for y in range(by, by + bh)]
        if all(g[y][x] == '.' for x, y in cells) and all(abs(x - spawn_col) > 1 for x, _ in cells) \
                and not any(x in fall_cols for x, _ in cells) \
                and not any(f"crumble {x * 8} " in c for c in crumbles for x, _ in cells):
            dashblocks.append(f"; dashblock {bx * 8} {by * 8} {bw * 8} {bh * 8} {int(random.random() < 0.85)}")
            for x, y in cells:
                g[y][x] = 'd'

# dream blocks (seed % 4 == 1, so they meet both the zip movers of the even
# rooms and the falling blocks of the odd ones): boxes in the air, solid unless
# she dashes into them. Placed before the markers above are cleared, so they
# cannot land on a crumble or dash block.
dreamblocks = []
if seed % 4 == 1:
    fall_cols = used if seed % 2 == 1 else set()
    want = random.randint(1, 3)
    for _ in range(40):
        if len(dreamblocks) == want:
            break
        bw, bh = random.randint(1, 4), random.randint(1, 3)
        bx, by = random.randint(1, W - 1 - bw), random.randint(1, H - 1 - bh)
        cells = [(x, y) for x in range(bx, bx + bw) for y in range(by, by + bh)]
        if all(g[y][x] == '.' for x, y in cells) and all(abs(x - spawn_col) > 1 for x, _ in cells) \
                and not any(x in fall_cols for x, _ in cells):
            dreamblocks.append(f"; dreamblock {bx * 8} {by * 8} {bw * 8} {bh * 8}")
            for x, y in cells:
                g[y][x] = 'm'
g = [[ch if ch not in 'dm' else '.' for ch in r] for r in g]

# a switch gate with its touch switches (seed % 7 == 2). The gate is a solid
# that sits still until every switch in the room has been touched, then moves
# once; it shares the zip movers' slots (MAX_ZIP_MOVERS), so at most one here.
# The switches go on open tiles just above a floor, where random play walks
# over them (their collider is 30 x 30, so about two tiles across).
gates, touches = [], []
if seed % 7 == 2 and len(zips) < 3:
    for _try in range(60):
        gw, gh = random.randint(2, 4), random.randint(1, 2)
        gx, gy = random.randint(1, W - 1 - gw), random.randint(2, H - 1 - gh)
        cells = [(x, y) for x in range(gx, gx + gw) for y in range(gy, gy + gh)]
        if any(g[y][x] != '.' for x, y in cells) or any(abs(x - spawn_col) <= 1 for x, _ in cells):
            continue
        nx = min(max(gx * 8 + random.choice([-48, -32, 32, 48]), 8), W * 8 - 8 - gw * 8)
        ny = min(max(gy * 8 + random.choice([-24, 0, 24]), 8), H * 8 - 8 - gh * 8)
        gates.append(f"; switchgate {gx * 8} {gy * 8} {gw * 8} {gh * 8} {nx} {ny}")
        for x, y in cells:
            g[y][x] = 't'
        break
    for _ in range(random.randint(1, 2)) if gates else []:
        for _try in range(60):
            x, y = random.randint(1, W - 2), random.randint(2, H - 2)
            if g[y][x] == '.' and g[y + 1][x] == '#':
                touches.append(f"; touchswitch {x * 8 + 4} {y * 8 + 4}")
                break
    if not touches:                      # a gate with no switch would never open
        gates = []
    g = [[ch if ch != 't' else '.' for ch in r] for r in g]

# a Badeline chaser (seed % 5 == 1): one line per chaser, each 0.4 s = 24
# frames further behind. The delays stay well inside CHASER_HIST_LEN.
chasers = []
if seed % 5 == 1:
    delay = random.randint(60, 120)
    chasers = [f"; chaser {delay}"] * random.randint(1, 2)

print("\n".join(exits + extra + springs + zips + gates + refills + falls + crumbles + dashblocks
                + dreamblocks + touches + chasers + ["".join(r) for r in g]))
