/*
 * celeste.h -- a C port of Madeline's movement (normal + dash states) from
 * Celeste's published Player.cs (github.com/NoelFB/Celeste, MIT licence) and
 * the Monocle engine pieces it relies on (Actor movement, Grid collision,
 * StateMachine/Coroutine timing, VirtualButton buffering, Engine freeze).
 *
 * The same source compiles into two things:
 *   - a concrete simulator (sim/), used to replay and check solutions, and
 *   - a CBMC harness (harness/), where inputs are nondeterministic and the
 *     SAT solver searches for the fastest input sequence.
 *
 * Every float operation mirrors the order of operations in the C# source so
 * that IEEE single-precision rounding matches the game. See README for the
 * list of things that are deliberately not modelled yet.
 */
#ifndef CELESTE_H
#define CELESTE_H

#include <stdbool.h>

/* ---- Engine ------------------------------------------------------------ */
/* XNA/FNA fixed timestep: TimeSpan.FromTicks(166667) -> (float)0.0166667   */
#define DT 0.0166667f

/* ---- Player.cs constants ---------------------------------------------- */
#define MAX_FALL                 160.0f
#define GRAVITY                  900.0f
#define HALF_GRAV_THRESHOLD       40.0f
#define FAST_MAX_FALL            240.0f
#define FAST_MAX_ACCEL           300.0f
#define MAX_RUN                   90.0f
#define RUN_ACCEL               1000.0f
#define RUN_REDUCE               400.0f
#define AIR_MULT                   0.65f
#define DUCK_FRICTION            500.0f
#define DUCK_CORRECT_CHECK         4
#define DUCK_CORRECT_SLIDE        50.0f
#define DODGE_SLIDE_SPEED_MULT     1.2f
#define DUCK_SUPER_JUMP_X_MULT     1.25f
#define DUCK_SUPER_JUMP_Y_MULT     0.5f
#define JUMP_GRACE_TIME            0.1f
#define JUMP_SPEED              (-105.0f)
#define JUMP_H_BOOST              40.0f
#define VAR_JUMP_TIME              0.2f
#define CEILING_VAR_JUMP_GRACE     0.05f
#define UPWARD_CORNER_CORRECTION   4
#define WALL_SPEED_RETENTION_TIME  0.06f
#define WALL_JUMP_CHECK_DIST       3
#define WALL_JUMP_FORCE_TIME       0.16f
#define WALL_JUMP_H_SPEED        (MAX_RUN + JUMP_H_BOOST)
#define WALL_SLIDE_START_MAX      20.0f
#define WALL_SLIDE_TIME            1.2f
#define SUPER_JUMP_H             260.0f
#define SUPER_WALL_JUMP_SPEED   (-160.0f)
#define SUPER_WALL_JUMP_VAR_TIME   0.25f
#define SUPER_WALL_JUMP_H        (MAX_RUN + JUMP_H_BOOST * 2)
#define DASH_SPEED               240.0f
#define END_DASH_SPEED           160.0f
#define END_DASH_UP_MULT           0.75f
#define DASH_TIME                  0.15f
#define DASH_COOLDOWN              0.2f
#define DASH_REFILL_COOLDOWN       0.1f
#define DASH_CORNER_CORRECTION     4
#define DASH_V_FLOOR_SNAP_DIST     3
#define DASH_ATTACK_TIME           0.3f
#define CLIMB_CHECK_DIST           2
#define DASH_FREEZE_TIME           0.05f   /* Celeste.Freeze(.05f) in DashBegin */
#define INPUT_BUFFER_TIME          0.08f   /* Input.Jump / Input.Dash buffer   */
#define MAX_DASHES                 1       /* Inventory.Dashes in chapters 1-? */

/* (float)(1 / sqrt(2)) as produced by Vector2.Normalize on (1,1) */
#define DIAG 0.70710677f

#define ST_NORMAL 0
#define ST_DASH   2

/* hitboxes: width 8, x offset -4; height 11 (normal) or 6 (ducking) */
#define HB_NORMAL_H 11
#define HB_DUCK_H    6

/* ---- Inputs ------------------------------------------------------------ */
typedef struct {
    signed char mx;   /* -1 left, 0, 1 right                    */
    signed char my;   /* -1 up,   0, 1 down (screen coordinates) */
    bool jump;
    bool dash;
} Input;

/* ---- State ------------------------------------------------------------- */
/* Timers are floats in the reference build and exact frame counters in the
 * solver build (see tools/gen_tables.c). */
#ifdef REFERENCE
typedef float Timer;
typedef float SlideTimer;   /* wallSlideTimer, seconds          */
#else
typedef int Timer;          /* frames left while the timer is > 0 */
typedef int SlideTimer;     /* frames since set to WallSlideTime  */
#endif

typedef struct {
    /* Actor */
    int   x, y;              /* integer position (feet, horizontal centre) */
    float remX, remY;        /* Actor.movementCounter (subpixels)          */
    float spdX, spdY;

    /* Player */
    int   state;             /* ST_NORMAL or ST_DASH */
    int   facing;            /* -1 or 1 */
    bool  ducking;
    bool  onGround;
    int   dashes;
    int   moveX;
    int   forceMoveX;
    int   wallSlideDir;
    bool  autoJump;
    bool  dashStartedOnGround;
    int   aimX, aimY;        /* lastAim as (sign x, sign y); diagonal => normalised */
    int   dashDirX, dashDirY;/* DashDir, same encoding */
    float beforeDashSpdX, beforeDashSpdY;
    float varJumpSpeed;
    float wallSpeedRetained;
    float maxFall;

    /* Player timers */
    Timer jumpGraceTimer;
    Timer varJumpTimer;
    bool  varJumpLong;       /* varJumpTimer was set to SuperWallJumpVarTime */
    Timer dashCooldownTimer;
    Timer dashRefillCooldownTimer;
    Timer dashAttackTimer;
    SlideTimer wallSlideTimer;
    Timer wallSpeedRetentionTimer;
    Timer forceMoveXTimer;

    /* StateMachine's coroutine (DashCoroutine) */
    bool  coActive;
    int   coStage;           /* 0: before 'yield null', 1: before dash body, 2: waiting DashTime */
    Timer coWait;

    /* Engine */
    Timer freezeTimer;

    /* VirtualButtons (Input.Jump, Input.Dash) */
    bool  prevJump, prevDash;
    Timer jumpBuf, dashBuf;  /* bufferCounter */
    bool  jumpEdge, dashEdge;/* node.Pressed this frame */

    /* outcome */
    bool  exited;            /* level transition out of the right edge */
    bool  dead;
} State;

/* Room geometry comes from room.h (generated by tools/make_room.py) */
void celeste_init(State *s, int spawnX, int spawnY);
void celeste_step(State *s, Input in);

#endif
