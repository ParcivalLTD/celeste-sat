/*
 * live.c -- which fields of a route's state after T frames can not change
 * the rest of the route? (for tools/windows.py)
 *
 *   live T route.tas
 *
 * Plays the route to frame T, then for each field that same_future_mask()
 * may leave out, replays the rest of the route from copies of that state
 * with the field set to other values. The field is dead at T when every copy
 * moves exactly like the route on every later frame (position, subpixels,
 * speed, state, ducking, dashes, facing) and, when the route leaves the
 * room, leaves in a state that same_future() cannot tell from the route's.
 * Prints the mask of dead fields. It is a test, not a proof: a window that
 * finds a faster route with these fields left out is always replayed.
 */
#include <assert.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MODEL_ASSUME(c) assert(c)
#include "../model/celeste.c"
#include "../model/state_eq.h"
#include "tas_io.h"
#ifdef START_STATE_FILE
#include START_STATE_FILE
#endif

#define MAX_FRAMES 100000
static Input frames[MAX_FRAMES];
static int nframes;

static bool same_run(State a, State b, int from)
{
    for (int f = from; f < nframes; f++) {
        celeste_step(&a, frames[f]);
        celeste_step(&b, frames[f]);
        if (a.x != b.x || a.y != b.y || a.remX != b.remX || a.remY != b.remY || a.spdX != b.spdX
            || a.spdY != b.spdY || a.state != b.state || a.ducking != b.ducking || a.dashes != b.dashes
            || a.facing != b.facing || a.exited != b.exited || a.dead != b.dead)
            return false;
        if (a.exited || a.dead) return same_future(&b, &a);
    }
    return same_future(&b, &a);
}

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: live T route.tas\n"); return 2; }
    int T = atoi(argv[1]);
    nframes = tas_load(argv[2], frames, MAX_FRAMES);
    State s;
#ifdef START_STATE_FILE
    s = START_STATE;
#else
    celeste_init(&s, SPAWN_X, SPAWN_Y);
#endif
    for (int f = 0; f < T && f < nframes; f++) celeste_step(&s, frames[f]);

    unsigned dead = 0;
#define TRY(bit, ...) do { bool ok = true; for (int v = 0; v < 64 && ok; v++) { State p = s; bool set = true; \
        switch (v) { __VA_ARGS__ default: set = false; } if (set) ok = same_run(s, p, T); } if (ok) dead |= (bit); } while (0)
    TRY(SF_ONGROUND, case 0: p.onGround = 0; break; case 1: p.onGround = 1; break;);
#ifdef REFERENCE
#error "live.c needs the solver build (integer timers)"
#endif
    TRY(SF_WALLSLIDE, case 0: p.wallSlideTimer = 0; break; case 1: p.wallSlideTimer = WS_KZ / 3; break;
                      case 2: p.wallSlideTimer = 2 * WS_KZ / 3; break; case 3: p.wallSlideTimer = WS_KZ; break;);
    TRY(SF_STAMINA, case 0: p.stamina = 110.0f; break; case 1: p.stamina = 70.0f; break; case 2: p.stamina = 25.0f; break;
                    case 3: p.stamina = 1.0f; break;);
    TRY(SF_JUMPGRACE, case 0: p.jumpGraceTimer = 0; break; case 1: p.jumpGraceTimer = 2; break;
                      case 2: p.jumpGraceTimer = 4; break; case 3: p.jumpGraceTimer = K_JUMP_GRACE_TIME; break;);
    TRY(SF_VARJUMP, case 0: p.varJumpTimer = 0; break; case 1: p.varJumpTimer = 4; break;
                    case 2: p.varJumpTimer = 8; break; case 3: p.varJumpTimer = K_VAR_JUMP_TIME; break;
                    case 4: p.varJumpTimer = 6; p.varJumpSpeed = -105.0f; break;
                    case 5: p.varJumpTimer = 6; p.varJumpSpeed = -160.0f; p.varJumpLong = true; break;);
    TRY(SF_DASHCD, case 0: p.dashCooldownTimer = 0; break; case 1: p.dashCooldownTimer = 4; break;
                   case 2: p.dashCooldownTimer = 8; break; case 3: p.dashCooldownTimer = K_DASH_COOLDOWN; break;);
    TRY(SF_DASHREFILLCD, case 0: p.dashRefillCooldownTimer = 0; break; case 1: p.dashRefillCooldownTimer = 3; break;
                         case 2: p.dashRefillCooldownTimer = K_DASH_REFILL_COOLDOWN; break;);
    TRY(SF_DASHATTACK, case 0: p.dashAttackTimer = 0; break; case 1: p.dashAttackTimer = 6; break;
                       case 2: p.dashAttackTimer = 12; break; case 3: p.dashAttackTimer = K_DASH_ATTACK_TIME; break;);
    TRY(SF_RETENTION, case 0: p.wallSpeedRetentionTimer = 0; break;
                      case 1: p.wallSpeedRetentionTimer = K_WALL_SPEED_RETENTION_TIME; p.wallSpeedRetained = 150.0f; break;
                      case 2: p.wallSpeedRetentionTimer = K_WALL_SPEED_RETENTION_TIME; p.wallSpeedRetained = -150.0f; break;);
    TRY(SF_FORCEMOVE, case 0: p.forceMoveXTimer = 0; break;
                      case 1: p.forceMoveXTimer = 5; p.forceMoveX = 1; break; case 2: p.forceMoveXTimer = 5; p.forceMoveX = -1; break;
                      case 3: p.forceMoveXTimer = K_WALL_JUMP_FORCE_TIME; p.forceMoveX = 0; break;);
    TRY(SF_WALLBOOST, case 0: p.wallBoostTimer = 0; break;
                      case 1: p.wallBoostTimer = 6; p.wallBoostDir = 1; break; case 2: p.wallBoostTimer = 6; p.wallBoostDir = -1; break;);
    TRY(SF_MAXFALL, case 0: p.maxFall = MAX_FALL; break; case 1: p.maxFall = 200.0f; break; case 2: p.maxFall = FAST_MAX_FALL; break;);
    TRY(SF_AUTOJUMP, case 0: p.autoJump = 0; break; case 1: p.autoJump = 1; break;);
    TRY(SF_MOVEX, case 0: p.moveX = -1; break; case 1: p.moveX = 0; break; case 2: p.moveX = 1; break;);
    TRY(SF_FACING, case 0: p.facing = -1; break; case 1: p.facing = 1; break;);
    TRY(SF_HOPWAIT, case 0: p.hopWaitX = -1; break; case 1: p.hopWaitX = 0; break; case 2: p.hopWaitX = 1; break;);
    TRY(SF_DASHDIR, case 0: p.dashDirX = 0; p.dashDirY = 0; break; case 1: p.dashDirX = 0; p.dashDirY = -1; break;
                    case 2: p.dashDirX = 1; p.dashDirY = 0; break; case 3: p.dashDirX = -1; p.dashDirY = 0; break;
                    case 4: p.dashDirX = 1; p.dashDirY = -1; break; case 5: p.dashDirX = -1; p.dashDirY = -1; break;
                    case 6: p.dashDirX = 1; p.dashDirY = 1; break; case 7: p.dashDirX = 0; p.dashDirY = 1; break;);
    printf("%u\n", dead);
    return 0;
}
