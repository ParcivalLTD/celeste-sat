/*
 * chain.c -- replay one input file across a room transition: room A (from
 * START or its spawn), the transition, then room B, with the same model
 * builds as harness/cross.c (written by tools/cross.py).
 *
 *   chain inputs.tas [-t]          prints the frame she leaves A and B
 *   -t                             also prints the first frame in B whose
 *                                  state is TARGET (same_future)
 *   -s K out.h                     writes the state after K frames (in A or B)
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "celeste.h"
#include "tables.h"
#include "cross_setup.h"
#include "transition.h"
#include "state_eq.h"
#include "tas_io.h"

void a_step(State *s, Input in);
void b_step(State *s, Input in);

static Input frames[100000];

static void dump(const State *s, const char *path, int k)
{
    FILE *f = fopen(path, "w");
    if (!f) { perror(path); exit(1); }
#define I(n) fprintf(f, "    .%s = %d,\n", #n, (int)s->n)
#define F(n) fprintf(f, "    .%s = %af,\n", #n, (double)s->n)
    fprintf(f, "/* state after %d frames (written by chain -s) */\n#define START_FRAMES %d\n", k, k);
    fprintf(f, "static const State START_STATE = {\n");
    I(x); I(y); F(remX); F(remY); F(spdX); F(spdY);
    F(liftSpeedX); F(liftSpeedY); F(liftLastX); F(liftLastY); I(liftGraceTimer);
    fprintf(f, "    .zipTimer = {");
    for (int z = 0; z < MAX_ZIP_MOVERS; z++) fprintf(f, "%s%d", z ? ", " : "", (int)s->zipTimer[z]);
    fprintf(f, "},\n");
    I(hopZip); I(hopZipT);
    fprintf(f, "    .refillTimer = {");
    for (int z = 0; z < MAX_REFILLS; z++) fprintf(f, "%s%d", z ? ", " : "", (int)s->refillTimer[z]);
    fprintf(f, "},\n");
    I(state); I(facing); I(ducking); I(onGround); I(dashes); I(moveX); I(forceMoveX); I(wallSlideDir);
    I(autoJump); I(dashStartedOnGround); I(aimX); I(aimY); I(dashDirX); I(dashDirY);
    F(beforeDashSpdX); F(beforeDashSpdY); F(varJumpSpeed); F(wallSpeedRetained); F(maxFall);
    F(stamina); I(wallBoostDir); I(lastClimbMove); I(hopWaitX);
    I(jumpGraceTimer); I(varJumpTimer); I(varJumpLong); I(dashCooldownTimer); I(dashRefillCooldownTimer);
    I(dashAttackTimer); I(wallSlideTimer); I(wallSpeedRetentionTimer); I(forceMoveXTimer);
    I(wallBoostTimer); I(climbNoMoveTimer);
    I(coActive); I(coStage); I(coWait); I(freezeTimer); I(prevJump); I(prevDash); I(prevCDash);
    I(jumpBuf); I(dashBuf); I(cdashBuf); I(jumpEdge); I(dashEdge); I(cdashEdge); I(demoDashed);
    I(exited); I(dead);
    fprintf(f, "};\n");
    fclose(f);
#undef I
#undef F
}

int main(int argc, char **argv)
{
    const char *path = NULL, *out = NULL;
    int at = -1, target = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-t")) target = 1;
        else if (!strcmp(argv[i], "-s") && i + 2 < argc) { at = atoi(argv[++i]); out = argv[++i]; }
        else path = argv[i];
    }
    if (!path) { fprintf(stderr, "usage: chain inputs.tas [-t] [-s K out.h]\n"); return 2; }
    int n = tas_load(path, frames, 100000);
    State s = START;
    int inB = 0, exitA = -1, exitB = -1, hitAt = -1;
    for (int f = 0; f < n; f++) {
        if (!inB) {
            a_step(&s, frames[f]);
            if (s.dead) { printf("died in room A at frame %d\n", f + 1); return 1; }
            if (s.exited) { exitA = f + 1; s = enter_room(s); inB = 1; }
        } else {
            b_step(&s, frames[f]);
            if (s.dead) { printf("died in room B at frame %d\n", f + 1); return 1; }
            if (target && hitAt < 0 && same_future(&s, &TARGET)) hitAt = f + 1;
            if (s.exited) { exitB = f + 1; }
        }
        if (out && f + 1 == at) dump(&s, out, at);
        if (exitB > 0) break;
    }
    printf("left room A on frame %d\n", exitA);
    if (target) printf("known route's room-B state reached on frame %d\n", hitAt);
    if (exitB > 0) printf("EXIT at frame %d\n", exitB);
    else printf("no exit from room B within %d frames\n", n);
    return exitB > 0 ? 0 : 1;
}
