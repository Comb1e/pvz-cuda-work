# Supported PC mechanics and reconstruction limits

At 100 Hz a tick is 0.01 seconds. Timers below belong to the simulator, not
to a learning agent's inputs. All ranges include both endpoints.

| Mechanic | Implemented contract |
|---|---|
| Sunflower | First production after 300–1,250 ticks; subsequent intervals 2,350–2,500; 25 sun |
| Sky | First 425–700 ticks; after drop n, min(950,425+10*n)+uniform(0,274) ticks |
| Pea/snow launch cycle | Initial phase 0–150; subsequent cycles 136–150; 32-tick windup after finding a target |
| Repeater | 25-tick windup; extra launch when cycle has 25 ticks remaining |
| Cherry | 100-tick fuse; immune to ordinary bites while fusing |
| Mine | 1,500 ticks underground, then 106 ticks rising, then armed |
| Chomper | Hit after 70 ticks; remainder of 105-tick bite animation; 4,000-tick digestion; 234-tick recovery; misses a capable pole carrier or vaulter |
| Cards | Initial nut/mine delay 2,001 ticks; cherry 3,501; later recharge is configured 750/3,000/5,000 plus one tick |
| Body/armor | Ordinary body 270, pole body 500; cone armor 370, bucket armor 1,100 |
| Head loss | Body health strictly below integer(maximum/3); counts as neutralized once |
| Autonomous decay | Each headless body's tick has probability 1/5 of losing 1 HP, or 3 HP for body maximum at least 500 |
| Bites | Four HP every fourth zombie-age tick, or every eighth while chilled |
| Chilling | Gait animation rate 1/2, duration 1,000 ticks |

The card's extra tick follows the source's strict `counter > refreshTime`
comparison. A plant placed at tick t has its cooldown decremented on the next
advancing tick; instantaneous actions do not consume that tick.

Frame markers in the inspected animation reference give mine rise 19 frames
at 18 fps, chomper bite 25 at 24 fps, and recovery 28 at 12 fps. Round each
duration upward to a complete simulation tick: 106, 105 and 234 respectively.
Art is drawn independently; source artwork is not redistributed.

Movement and combat geometry are derived in [gait and geometry](gait-and-geometry.md).
The independent numerical tracks retain nonuniform motion, zero/negative segments,
loop endpoints and restart sampling. This is a fixed-point reconstruction, not
binary-compatible PC/GOTY simulation. Projectiles and mower base speeds retain
rounded 3.33*100/80 = 4.1625 tiles/s. Mower hit slowdown follows the existing
inverse-quadratic envelope. Custom mower/house boundaries are explicit limits.

Gameplay randomness is per-game xorshift32, with unsigned 32-bit shifts
13,17,5. Seed initialization is `(seed xor 0x9e3779b9) mod 2^32`, replacing
zero with one. Range sampling uses the remainder modulo range width. It has
a tiny modulo bias and does not reproduce the original game's RNG sequence.
Python and CUDA use identical calls in entity insertion order and serialize
the exact stream state, sky deadline and drop count. Scenario generation has
a separate RNG. Neither stream is an agent input.

`ZombieDefeated` denotes first neutralization by a headed-to-headless/dead
transition. `ZombieHeadLost` describes a surviving body. `ZombieDecayed`
records autonomous damage without a plant source; `ZombieRemoved` removes a
body without another defeat. Remaining/alive counts describe threats. Public
zombie lists also contain headless bodies until removal. They cannot bite,
start a vault, trigger an idle mower or cause a house breach. Victory requires
all scheduled threats neutralized and may leave visible headless bodies.
