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

/* game frames between the exit frame's update and her first update in the new
 * room; TRANSITION_GAP in tools/chapter.py (recordings/celeste-sat-probe-1to2.txt) */
#define TR_TRANSITION_GAP 40

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
            e.varJumpShort = false;
            e.dashCooldownTimer = K_DASH_COOLDOWN;
        } else {
            if (e.spdY < 0.0f) e.spdY = 0.0f;
            e.autoJump = false;
            e.varJumpTimer = 0;
        }
    }
    /* Level.TransitionRoutine: where she stops in the new room */
    if (TR_SIDE == TR_UP)    { int stop = TR_NEW_H <= 184 ? TR_NEW_H - 9 : TR_NEW_H - 5; if (y > stop) y = stop; }  /* measured, see tools/chapter.py */
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
    for (int i = 0; i < MAX_FALL_BLOCKS; i++) e.fbT[i] = 0;
    for (int i = 0; i < MAX_CRUMBLES; i++) e.crT[i] = 0;
    e.dbBroken = 0;
    e.tsOn = 0;
    e.hopZip = 0; e.hopZipT = 0;
    for (int i = 0; i < MAX_REFILLS; i++) e.refillTimer[i] = 0;
    /* a dream dash cannot survive the transition (she comes out in ST_NORMAL) */
    e.dreamDashCanEndTimer = 0;
    e.dreamJump = false;
    /* The Badeline chasers follow the positions she recorded (Player.ChaserStates)
     * with a delay in game time, and that history runs on across rooms: it is
     * carried over in the new room's coordinates, then TRANSITION_GAP frames of
     * standing at the entry position (the transition itself runs no player
     * updates). Mirrors carry_chaser_history in tools/chapter.py, which
     * documents it; tools/cross.py checks that the two agree. */
    {
        const int n = CHASER_HIST_LEN, t = st.chaserTimer;
        /* The new history is oldest-first with chaserTimer = n, so entry j
         * stands for n - 1 - j frames ago. The newest TR_TRANSITION_GAP of
         * them are the entry position; before that comes the old room's
         * history, which ends at index n - 1 - TR_TRANSITION_GAP. */
        for (int j = 0; j < n; j++) {
            int src = j + TR_TRANSITION_GAP;
            if (src < n && t > 0) {
                int i = (t - n + src) & CHASER_HIST_MASK;
                e.histX[j] = (short)(st.histX[i] + TR_DX);
                e.histY[j] = (short)(st.histY[i] + TR_DY);
            } else {                             /* the transition, or no chaser in the old room */
                e.histX[j] = (short)x;
                e.histY[j] = (short)y;
            }
        }
        e.chaserTimer = (short)n;
    }
    return e;
}

#endif
