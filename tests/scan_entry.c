/*
 * scan_entry.c -- for tests/chain_3b_5.py: play a route from a family of
 * entry states (an up-transition entry with x and the pending wall speed
 * retention varied) and dump the exit state of every one that leaves the
 * room on the route's last frame.
 *
 *   scan_entry route.tas OUTDIR X0 X1 RET0 RET1 RETSTEP
 *
 * Built against a room's room.h/tables.h, with START_STATE_FILE = a template
 * entry (its other fields are kept).
 */
#define main sim_main
#include "../sim/sim.c"
#undef main

int main(int argc, char **argv)
{
    if (argc < 8) { fprintf(stderr, "usage: scan_entry route.tas OUTDIR X0 X1 RET0 RET1 RETSTEP\n"); return 2; }
    int n = tas_load(argv[1], frames, MAX_FRAMES);
    int x0 = atoi(argv[3]), x1 = atoi(argv[4]), r0 = atoi(argv[5]), r1 = atoi(argv[6]), rs = atoi(argv[7]);
    int found = 0;
    for (int x = x0; x <= x1; x++)
        for (int ret = r0; ret <= r1; ret += rs) {
            State s = START_STATE;
            s.x = x; s.y = ROOM_H * 8 - 9; s.facing = 1; s.dashAttackTimer = 0;
            s.wallSpeedRetained = (float)ret; s.wallSpeedRetentionTimer = 4;
            int f;
            for (f = 0; f < n && !s.exited && !s.dead; f++) celeste_step(&s, frames[f]);
            if (!s.exited || f != n) continue;
            char path[4096];
            snprintf(path, sizeof path, "%s/exit_x%d_r%d.h", argv[2], x, ret);
            dump_state(&s, path, n);
            found++;
        }
    printf("%d entries leave on frame %d\n", found, n);
    return 0;
}
