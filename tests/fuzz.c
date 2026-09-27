/* fuzz.c -- random input sequences through the model; prints the exact state
 * every frame (floats as hex) so two builds can be diffed. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#define MODEL_ASSUME(c) assert(c)
#include "../model/celeste.c"

static unsigned long long rng;
static unsigned rnd(void) { rng = rng * 6364136223846793005ULL + 1442695040888963407ULL; return (unsigned)(rng >> 33); }

int main(int argc, char **argv)
{
    rng = strtoull(argv[1], 0, 10);
    int runs = atoi(argv[2]), frames = atoi(argv[3]);
    for (int r = 0; r < runs; r++) {
        State s;
        celeste_init(&s, SPAWN_X, SPAWN_Y);
        Input in = {0};
        int hold = 0;
        for (int f = 0; f < frames; f++) {
            if (hold-- <= 0) {
                hold = rnd() % 12;
                in.mx = (signed char)((int)(rnd() % 5) - 1); if (in.mx > 1) in.mx = 1; /* bias right */
                in.my = (signed char)((int)(rnd() % 3) - 1);
                in.jump = rnd() % 3 == 0;
                in.dash = rnd() % 6 == 0;
            } else if (rnd() % 4 == 0) {   /* occasional single-frame changes */
                in.jump = rnd() % 2; in.dash = rnd() % 5 == 0;
            }
            celeste_step(&s, in);
            printf("%d %d %d %a %a %a %a %d %d %d %d %d %d\n", r, s.x, s.y, s.remX, s.remY, s.spdX, s.spdY,
                   s.state, s.ducking, s.onGround, s.dashes, s.exited, s.dead);
            if (s.exited || s.dead) break;
        }
    }
#ifdef COVERAGE
    for (int k = 0; k < C_NCOV; k++) fprintf(stderr, "%s\t%ld\n", COV_NAMES[k], COVC[k]);
#endif
    return 0;
}
