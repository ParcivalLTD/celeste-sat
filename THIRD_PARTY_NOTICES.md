# Third-party notices

`model/celeste.c` and `model/celeste.h` port code from two MIT-licensed projects.

## Celeste `Player.cs` (github.com/NoelFB/Celeste)

```
MIT License

Copyright (c) 2018 Noel Berry

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```

## Monocle engine (Actor movement, Grid collision, StateMachine, Coroutine, VirtualButton)

```

Copyright (c) 2012-2014 Matt Thorson

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

The MIT licence covers that source code only, not the commercial Celeste game or its assets.

## References (nothing copied)

- The official Celeste changelogs (celestegame.com/changelog.html) for the
  movement changes after the published `Player.cs`.
- Extended Variant Mode (github.com/maddie480/ExtendedVariantMode) and
  GravityHelper (github.com/swoolcock/GravityHelper), whose patches of the
  current game's `Player` methods show the shape of those changes (wall
  bounce reach, corner correction reach, spike checks on dash corrections).
- VampireFlower/CelesteTAS (community TAS inputs) and celeste-rl (a recording
  from the real game) are downloaded by `tests/community_tas.py` and
  `tests/real_game.py` when the checks run; neither is included here.
