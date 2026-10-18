/*
 * edge_reach.c -- exact version of experiments/edge_windows.py's question for
 * the first T frames of a window: from the route's state after K frames, does
 * any input sequence of at most T frames make the model with the tiles
 * outside the room (now) and the model without them (commit 9e3dd4f: outside
 * = air) part ways?
 *
 *   edge_reach route.tas T K0 K1
 *
 * Linked with two builds of the model (solver build, prefixes new_ and old_:
 * the room's room.h, and the same room without its "; outside" lines),
 * written by edge_windows.py. Every frame of every input sequence is stepped
 * in both; while the two states stay identical, so does everything after
 * them (the state is the whole future), so "no" means the window's first T
 * frames are the old model's, whatever the inputs.
 *
 * One line per K: "K yes frame t states N" if the two models part ways
 * within T frames, else "K no states N vmax VX VY lift LX LY pos x,y ...":
 * the largest speeds the states after T frames carry (spdX,
 * wallSpeedRetained, beforeDashSpdX; spdY, beforeDashSpdY, varJumpSpeed: as
 * speed_bounds_from in harness/input_rules.h), the largest lift speeds they
 * carry (sideways, upwards) and her distinct positions then (alive and still
 * in the room), which edge_windows.py floods on for the rest.
 *
 * Breadth-first over every input (L/R x U/D x Jump, Dash, Crouch Dash each
 * off, held or pressed again x Grab: 486 per frame), duplicate states merged
 * by comparing the whole State. States that died or left the room are not
 * expanded. Exhaustive: no state is ever dropped.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "celeste.h"
#include "tas_io.h"
#ifdef START_STATE_FILE
#include START_STATE_FILE
#endif

void new_init(State *s);
void new_step(State *s, Input in);
void old_step(State *s, Input in);

#define MAX_FRAMES 100000
static Input frames[MAX_FRAMES];

static uint64_t hash_bytes(const void *p, size_t n)
{
    const unsigned char *b = p;
    uint64_t h = 1469598103934665603ULL;
    for (size_t i = 0; i < n; i++) h = (h ^ b[i]) * 1099511628211ULL;
    return h;
}

/* a set of States: open addressing over indices into a growable array */
typedef struct { State *v; size_t n, cap; int64_t *slot; size_t nslot; } Set;

static void set_clear(Set *s)
{
    s->n = 0;
    if (s->slot) memset(s->slot, 0xff, s->nslot * sizeof *s->slot);
}
static void set_grow(Set *s)
{
    size_t ns = s->nslot ? s->nslot * 2 : 1 << 16;
    free(s->slot);
    s->slot = malloc(ns * sizeof *s->slot);
    if (!s->slot) { fprintf(stderr, "out of memory\n"); exit(3); }
    memset(s->slot, 0xff, ns * sizeof *s->slot);
    s->nslot = ns;
    for (size_t i = 0; i < s->n; i++) {
        size_t j = hash_bytes(&s->v[i], sizeof(State)) & (ns - 1);
        while (s->slot[j] >= 0) j = (j + 1) & (ns - 1);
        s->slot[j] = (int64_t)i;
    }
}
static void set_add(Set *s, const State *st)
{
    if (2 * (s->n + 1) > s->nslot) set_grow(s);
    size_t j = hash_bytes(st, sizeof(State)) & (s->nslot - 1);
    while (s->slot[j] >= 0) {
        if (!memcmp(&s->v[s->slot[j]], st, sizeof(State))) return;
        j = (j + 1) & (s->nslot - 1);
    }
    if (s->n == s->cap) {
        s->cap = s->cap ? s->cap * 2 : 1 << 12;
        s->v = realloc(s->v, s->cap * sizeof(State));
        if (!s->v) { fprintf(stderr, "out of memory\n"); exit(3); }
    }
    s->v[s->n] = *st;
    s->slot[j] = (int64_t)s->n++;
}

static float fabs_(float v) { return v < 0 ? -v : v; }

int main(int argc, char **argv)
{
    if (argc != 5) { fprintf(stderr, "usage: edge_reach route.tas T K0 K1\n"); return 2; }
    int n = tas_load(argv[1], frames, MAX_FRAMES);
    int T = atoi(argv[2]), k0 = atoi(argv[3]), k1 = atoi(argv[4]);
    const unsigned char btn[3] = { 0, 1, BTN_REPRESS };
    Set a = {0}, b = {0};
    for (int k = k0; k <= k1 && k <= n; k++) {
        State s;
        memset(&s, 0, sizeof s);
#ifdef START_STATE_FILE
        s = START_STATE;
#else
        new_init(&s);
#endif
        for (int f = 0; f < k; f++) {
            State o = s;
            new_step(&s, frames[f]);
            old_step(&o, frames[f]);
            if (memcmp(&s, &o, sizeof s)) {
                fprintf(stderr, "K %d: the route itself parts the two models on frame %d\n", k, f + 1);
                return 4;
            }
        }
        set_clear(&a);
        set_add(&a, &s);
        size_t total = 1;
        int hit = 0;
        for (int t = 1; t <= T && !hit && a.n; t++) {
            set_clear(&b);
            for (size_t i = 0; i < a.n && !hit; i++)
                for (int c = 0; c < 486 && !hit; c++) {
                    Input in = { .mx = (signed char)(c % 3 - 1), .my = (signed char)(c / 3 % 3 - 1),
                                 .jump = btn[c / 9 % 3], .dash = btn[c / 27 % 3], .cdash = btn[c / 81 % 3],
                                 .grab = c / 243 };
                    State nx = a.v[i], ox = a.v[i];
                    new_step(&nx, in);
                    old_step(&ox, in);
                    if (memcmp(&nx, &ox, sizeof nx)) hit = t;
                    else if (!nx.dead && !nx.exited) set_add(&b, &nx);
                }
            total += b.n;
            if (getenv("EDGE_VERBOSE")) fprintf(stderr, "  K %d frame %d: %zu states\n", k, t, b.n);
            Set tmp = a; a = b; b = tmp;
        }
        if (hit) {
            printf("%d yes frame %d states %zu\n", k, hit, total);
        } else {
            float vx = 0, vy = 0, lx = 0, ly = 0;
            for (size_t i = 0; i < a.n; i++) {
                const State *q = &a.v[i];
                const float xs[] = { q->spdX, q->wallSpeedRetained, q->beforeDashSpdX };
                const float ys[] = { q->spdY, q->beforeDashSpdY, q->varJumpSpeed };
                for (int j = 0; j < 3; j++) {
                    if (fabs_(xs[j]) > vx) vx = fabs_(xs[j]);
                    if (fabs_(ys[j]) > vy) vy = fabs_(ys[j]);
                }
                const float l[] = { q->liftSpeedX, q->liftLastX }, u[] = { q->liftSpeedY, q->liftLastY };
                for (int j = 0; j < 2; j++) {
                    if (fabs_(l[j]) > lx) lx = fabs_(l[j]);
                    if (-u[j] > ly) ly = -u[j];
                }
            }
            printf("%d no states %zu vmax %.3f %.3f lift %.3f %.3f pos", k, total, vx, vy, lx, ly);
            for (size_t i = 0; i < a.n; i++) {
                bool dup = false;                      /* nearby duplicates only; the reader merges the rest */
                for (size_t j = i; j-- > 0 && j + 64 > i;)
                    if (a.v[j].x == a.v[i].x && a.v[j].y == a.v[i].y) { dup = true; break; }
                if (!dup) printf(" %d,%d", a.v[i].x, a.v[i].y);
            }
            printf("\n");
        }
        fflush(stdout);
    }
    return 0;
}
