/*
 * sim.c -- concrete simulator. Replays a CelesteTAS-style input file through
 * the same model the solver uses and reports when Madeline leaves the room.
 *
 *   sim [-v] [-j trace.json] [-s K start.h] inputs.tas
 *
 * -s K start.h  writes the exact state after K frames as a C initializer, so
 *               the solver can start from the middle of a run.
 *
 * Input lines look like "  12,R,J" (frame count, then any of L R U D J X).
 * J/K = jump, X/C = dash. Lines starting with '#' are comments.
 */
#include <assert.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MODEL_ASSUME(c) assert(c)
#include "../model/celeste.c"

#define MAX_FRAMES 100000
static Input frames[MAX_FRAMES];

static void dump_state(const State *s, const char *path, int k)
{
#ifdef REFERENCE
    fprintf(stderr, "-s needs the solver build\n"); (void)s; (void)path; (void)k; exit(2);
#else
    FILE *f = fopen(path, "w");
    if (!f) { perror(path); exit(1); }
#define I(n) fprintf(f, "    .%s = %d,\n", #n, (int)s->n)
#define F(n) fprintf(f, "    .%s = %af,\n", #n, (double)s->n)
    fprintf(f, "/* state after %d frames (written by sim -s) */\n#define START_FRAMES %d\n", k, k);
    fprintf(f, "static const State START_STATE = {\n");
    I(x); I(y); F(remX); F(remY); F(spdX); F(spdY);
    I(state); I(facing); I(ducking); I(onGround); I(dashes); I(moveX); I(forceMoveX); I(wallSlideDir);
    I(autoJump); I(dashStartedOnGround); I(aimX); I(aimY); I(dashDirX); I(dashDirY);
    F(beforeDashSpdX); F(beforeDashSpdY); F(varJumpSpeed); F(wallSpeedRetained); F(maxFall);
    I(jumpGraceTimer); I(varJumpTimer); I(varJumpLong); I(dashCooldownTimer); I(dashRefillCooldownTimer);
    I(dashAttackTimer); I(wallSlideTimer); I(wallSpeedRetentionTimer); I(forceMoveXTimer);
    I(coActive); I(coStage); I(coWait); I(freezeTimer); I(prevJump); I(prevDash); I(jumpBuf); I(dashBuf);
    I(jumpEdge); I(dashEdge); I(exited); I(dead);
    fprintf(f, "};\n");
    fclose(f);
#undef I
#undef F
#endif
}

static int load(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); exit(1); }
    char line[512];
    int n = 0;
    while (fgets(line, sizeof line, f)) {
        char *p = line;
        while (isspace((unsigned char)*p)) p++;
        if (*p == '#' || *p == 0) continue;
        int count = atoi(p);
        if (count <= 0) continue;
        Input in = {0};
        for (char *q = strchr(p, ','); q; q = strchr(q + 1, ',')) {
            char c = toupper((unsigned char)q[1]);
            if (c == 'L') in.mx = -1;
            else if (c == 'R') in.mx = 1;
            else if (c == 'U') in.my = -1;
            else if (c == 'D') in.my = 1;
            else if (c == 'J' || c == 'K') in.jump = true;
            else if (c == 'X' || c == 'C') in.dash = true;
            else if (c == 'G') { fprintf(stderr, "warning: grab is not modelled\n"); }
        }
        for (int i = 0; i < count && n < MAX_FRAMES; i++) frames[n++] = in;
    }
    fclose(f);
    return n;
}

int main(int argc, char **argv)
{
    int verbose = 0;
    const char *json = NULL, *path = NULL, *dump = NULL;
    int dumpAt = -1;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-v")) verbose = 1;
        else if (!strcmp(argv[i], "-j") && i + 1 < argc) json = argv[++i];
        else if (!strcmp(argv[i], "-s") && i + 2 < argc) { dumpAt = atoi(argv[++i]); dump = argv[++i]; }
        else path = argv[i];
    }
    if (!path) { fprintf(stderr, "usage: sim [-v] [-j trace.json] inputs.tas\n"); return 2; }

    int n = load(path);
    State s;
    celeste_init(&s, SPAWN_X, SPAWN_Y);

    FILE *jf = json ? fopen(json, "w") : NULL;
    if (jf) fprintf(jf, "{\"room_w\":%d,\"room_h\":%d,\"frames\":[\n"
                        "  {\"x\":%d,\"y\":%d,\"st\":%d,\"duck\":%d,\"frz\":0,\"vx\":0,\"vy\":0,\"in\":\"\",\"dashes\":%d,\"ground\":1}",
                    ROOM_W, ROOM_H, s.x, s.y, s.state, s.ducking, s.dashes);
    if (verbose)
        printf("frame  in     st  x    y    remX        remY        spdX         spdY        flags\n");

    int exitFrame = -1;
    if (dump && dumpAt == 0) dump_state(&s, dump, 0);
    for (int f = 0; f < n; f++) {
        Input in = frames[f];
        bool frozen = s.freezeTimer > 0;
        celeste_step(&s, in);
        if (verbose) {
            char ins[8] = "      ";
            ins[0] = in.mx < 0 ? 'L' : (in.mx > 0 ? 'R' : '.');
            ins[1] = in.my < 0 ? 'U' : (in.my > 0 ? 'D' : '.');
            ins[2] = in.jump ? 'J' : '.';
            ins[3] = in.dash ? 'X' : '.';
            printf("%5d  %s %s %4d %4d %11.7f %11.7f %12.6f %12.6f %s%s%s d%d\n", f + 1, ins,
                   frozen ? "frz" : (s.state == ST_DASH ? "DSH" : "NRM"),
                   s.x, s.y, s.remX, s.remY, s.spdX, s.spdY,
                   s.onGround ? "G" : "-", s.ducking ? "C" : "-", s.autoJump ? "A" : "-", s.dashes);
        }
        if (jf) {
            char ins[8]; int k = 0;
            if (in.mx < 0) ins[k++] = 'L'; if (in.mx > 0) ins[k++] = 'R';
            if (in.my < 0) ins[k++] = 'U'; if (in.my > 0) ins[k++] = 'D';
            if (in.jump) ins[k++] = 'J'; if (in.dash) ins[k++] = 'X';
            ins[k] = 0;
            fprintf(jf, ",\n  {\"x\":%d,\"y\":%d,\"st\":%d,\"duck\":%d,\"frz\":%d,\"vx\":%.4f,\"vy\":%.4f,"
                        "\"in\":\"%s\",\"dashes\":%d,\"ground\":%d}",
                    s.x, s.y, s.state, s.ducking, frozen, s.spdX, s.spdY, ins, s.dashes, s.onGround);
        }
        if (dump && f + 1 == dumpAt) dump_state(&s, dump, dumpAt);
        if (s.exited) { exitFrame = f + 1; break; }
        if (s.dead) { printf("died at frame %d\n", f + 1); break; }
    }
    if (jf) { fprintf(jf, "\n],\"exit_frame\":%d}\n", exitFrame); fclose(jf); }

    if (exitFrame > 0) printf("EXIT at frame %d\n", exitFrame);
    else printf("no exit within %d frames (x=%d y=%d)\n", n, s.x, s.y);
    return exitFrame > 0 ? 0 : 1;
}
