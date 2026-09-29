/*
 * transition.h -- the state Madeline enters the next room with (solver
 * build). The same rules as enter_room in tools/chapter.py, which documents
 * them; tools/cross.py checks that the two agree.
 *
 * The including file defines, for one room pair:
 *   TR_SIDE   TR_UP, TR_DOWN, TR_LEFT or TR_RIGHT: the edge she leaves by
 *   TR_DX/DY  old room origin - new room origin (world pixels)
 *   TR_NEW_W/H  size of the new room in pixels
 */
#ifndef TRANSITION_H
#define TRANSITION_H

#define TR_UP    0
#define TR_DOWN  1
#define TR_LEFT  2
#define TR_RIGHT 3

/* Math.Round: to nearest, ties to even (speeds are well inside +-2^22) */
static float tr_round_even(float v)
{
    float f = (float)(int)v;                 /* truncates towards zero */
    if (f > v) f -= 1.0f;                    /* floor */
    float d = v - f;                         /* exact, in [0, 1) */
    if (d > 0.5f) return f + 1.0f;
    if (d < 0.5f) return f;
    return ((int)f & 1) ? f + 1.0f : f;
}

static State enter_room(State st)
{
    State e = st;
    int x = st.x + TR_DX, y = st.y + TR_DY;

    if (TR_SIDE == TR_UP || TR_SIDE == TR_DOWN) {        /* BeforeUp/DownTransition */
        if (TR_SIDE == TR_UP) {
            e.spdX = 0.0f;
            e.spdY = e.varJumpSpeed = -105.0f;
        }
        if (e.state == ST_DASH) { e.coActive = false; e.coWait = 0; }   /* coroutine cancelled */
        if (e.state == ST_CLIMB) e.wallSpeedRetentionTimer = 0;          /* ClimbEnd */
        if (e.state != ST_NORMAL) { e.maxFall = 160.0f; e.state = ST_NORMAL; }  /* NormalBegin */
        if (TR_SIDE == TR_UP) {
            e.autoJump = true;
            e.varJumpTimer = K_VAR_JUMP_TIME;
            e.varJumpLong = false;
            e.dashCooldownTimer = K_DASH_COOLDOWN;
        } else {
            if (e.spdY < 0.0f) e.spdY = 0.0f;
            e.autoJump = false;
            e.varJumpTimer = 0;
        }
    }
    /* Level.TransitionRoutine: where she stops in the new room */
    if (TR_SIDE == TR_UP)    { if (y > TR_NEW_H - 9) y = TR_NEW_H - 9; }
    if (TR_SIDE == TR_DOWN)  { if (y < 12) y = 12; }
    if (TR_SIDE == TR_RIGHT) { if (x < 4) x = 4; }
    if (TR_SIDE == TR_LEFT)  { if (x > TR_NEW_W - 5) x = TR_NEW_W - 5; }
    if (TR_SIDE == TR_LEFT || TR_SIDE == TR_RIGHT) { if (y > TR_NEW_H - 1) y = TR_NEW_H - 1; }
    /* Player.TransitionTo, on arrival */
    e.x = x; e.y = y;
    e.remX = 0.0f; e.remY = 0.0f;
    e.spdX = tr_round_even(e.spdX);
    e.spdY = tr_round_even(e.spdY);
    /* Player.OnTransition */
    e.wallSlideTimer = 0;                    /* WallSlideTime (solver build: steps since set) */
    e.jumpGraceTimer = 0;
    e.forceMoveXTimer = 0;
    e.dashes = 1;                            /* RefillDash (MAX_DASHES) */
    e.stamina = 110.0f;                      /* RefillStamina */
    /* buttons released during the transition; buffers long expired */
    e.prevJump = e.prevDash = e.prevCDash = false;
    e.jumpBuf = e.dashBuf = e.cdashBuf = 0;
    e.jumpEdge = e.dashEdge = e.cdashEdge = false;
    e.demoDashed = false;
    e.exited = false; e.dead = false;
    e.freezeTimer = 0;
    /* the new room's moving solids start over (her lift speed stays with her) */
    for (int i = 0; i < MAX_ZIP_MOVERS; i++) e.zipTimer[i] = 0;
    e.hopZip = 0; e.hopZipT = 0;
    return e;
}

#endif
