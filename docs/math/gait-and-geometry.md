# Gait and geometry controls for 1.6.0

This is an independent fixed-point implementation of numerical facts inspected in
the PC/GOTY reconstruction, not executable equivalence. The references identify
the exact revisions. No animation artwork is distributed.

## Units and gait

One tile is 80 source pixels and 1,000 default simulation units. Public zombie
`x` denotes the left edge of the ordinary 42-pixel body rectangle. Its source
sprite origin is therefore `x * 80 / units - 36`, relative to the lawn origin.
Plant origins are `80 * column`; centers add 40 pixels. Rows are 100 pixels apart.
Zombie rectangles extend from row origin minus 30 to plus 85 pixels.
Custom spawn, house and mower boundaries remain explicit scenario conventions;
they do not reproduce original cutscene/spawn positions.

For source velocity v, N animation frames and ground-track displacement D pixels,
the inspected animation rate is r = 47 v N / D frames/second. Each 100 Hz tick
advances normalized phase by r/(100 N). Normal looping selects ground interval
floor(phase*(N-1)), not floor(phase*N). For ground delta d in that interval,
movement is d*r/100 pixels. The continuous-cycle mean is consequently
47*v*N/(80*(N-1)) tiles/second. It is not simply 47*v/80.

| Track | N | D pixels | v range | Mean tiles/second |
|---|---:|---:|---:|---:|
| ordinary walk / walk2 | 47 | 49.8 | .23–.32 | .1380625–.1920869565 |
| flag walk2 | 47 | 49.8 | .45 fixed | .2701222826 |
| pole running | 37 | 30 | .66–.68 | .3985208333–.4105972222 |
| pole walking | 45 | 67.8 | .23–.32 | .1381960227–.1922727273 |

Track deltas use tenths of a pixel, including zero and negative deltas. Velocity
uses thousandths of a source velocity unit. Phase and animation rate use 10^6
units. Rate is rounded down once; phase and displacement retain division
remainders. Signed division is floor division on both CPU and CUDA. Thus a
negative pole-walk segment does not silently become zero. The constant movement
denominator is 80,000 * 10^6; changing chilling does not discard its remainder.
Chilling halves the animation rate. Two chilled ticks reproduce one ordinary
phase increment, subject to explicitly retained rounding, rather than a 40%
velocity multiplier. Restarting a walk samples a fresh speed and track variant;
flag velocity is fixed. Gameplay RNG remains xorshift32, not the PC RNG.

Pole jumping has 43 frames at 24 fps: ceil(4300/24) = 180 ticks. In-flight
translation uses the source velocity `(sprite_x - plant_x - 80)/(4300/24)`;
it is independent of chilling. The completion shift is 150 pixels, not one
80-pixel tile. The landing translation is kept separate from the jump phase.
Head loss drops the visible pole but preserves the locomotion phase.

## Geometry and boundary controls

Use the same conversion for every participant, with integer cross-products to
avoid independently rounding half-pixel boundaries. Ordinary zombie attacks are
[sprite_x+50,sprite_x+70]; pole pre-vault attacks are [sprite_x-29,sprite_x+41].
Plant bodies are [plant_x+10,plant_x+70]. Required overlap is at least 20 pixels.
For a left-moving body edge, first ordinary contact is plant_x+36; first pole
contact is plant_x+115. Equality qualifies; one unit outside does not.

Plant target intervals are [plant_x+60,infinity) for peas, [plant_x,plant_x+55]
for mines and [plant_x+80,plant_x+120] for chomper. Mine triggering excludes
headless bodies and both pre-vault/in-vault phases. Post-vault mine range starts
40 pixels later; a biting target adds 30 pixels of tolerance. Chomper adds 60
pixels while biting or against a biting target. Mine blasts also exclude airborne vaulters (damage flags 77 lack bit 4);
cherry blasts include them (127). Blast eligibility is separate:
a grounded pole carrier can receive another zombie's mine blast.

Cherry centers at (plant_x+40,row_y+40), radius 115, row distance <=1. Mine
centers at (plant_x+20,row_y+40), radius 60, same row. For rectangle [l,r]×[t,b],
dx=max(l-cx,0,cx-r), dy=max(t-cy,0,cy-b); hit iff dx²+dy²<=radius². Tangency
qualifies. Peas have horizontal bounds [shot_x-15,shot_x+40], and cannot hit
airborne vaulters. Continuous sweeps prevent tunnelling in configurable fast
test scenarios. Headless autonomous damage has no plant source or reward.

## Audit limits

Production, recharge, body/armor health, launch cycles, biting and head-loss
thresholds retain the controls in [PC mechanics](pc-mechanics.md). Corrected
discrepancies are gait/loop endpoints, slowing, restart sampling, pole geometry,
target eligibility and circular blasts. Remaining approximations include integer
RNG, fixed-point timing, visual blending, unsupported entities, source sprite
integer truncation and custom level/house/mower positioning. These controls do
not establish equivalence to an original commercial executable.

Mower `x` is its leading edge. The body interval is [x-50,x] source pixels;
strictly positive overlap with zombie [x,x+42] triggers or damages. Sweeping
through the next position prevents crossing misses. The ready-mower location
and house boundary remain the existing custom rules, rather than original
cutscene coordinates.
