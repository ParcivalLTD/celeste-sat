#!/usr/bin/env python3
"""Random enclosed room with an exit opening on the right, for fuzzing."""
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
ey = random.randint(2, H - 3)                            # exit: 2-3 tiles tall
for y in range(ey, min(ey + random.randint(2, 3), H - 1)): g[y][W-1] = '.'
g[H-2][1] = g[H-3][1] = g[H-4][1] = '.'                  # spawn column clear
g[H-2][1] = 'S'
if random.random() < 0.3:                                 # sometimes a pit
    px = random.randint(3, W - 4); g[H-1][px] = '.'
print("\n".join("".join(r) for r in g))
