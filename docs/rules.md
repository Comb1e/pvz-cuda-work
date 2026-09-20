# Daytime rules — daytime-1.0

The shipped balance is a documented PvZ-style preset, not a timing-perfect reproduction
of the original game. All players and external controllers use the same rules.

## Economy and plants

Five rows, nine columns, 50 starting sun, cap 9,990. Sky sun credits 25 every ten seconds.
All eight cards start ready. Recharge is shared by all placements of that plant type.
Each tile holds one plant. Digging refunds nothing and does not clear recharge.

| Plant | Cost | Recharge | Health | Behavior |
|---|---:|---:|---:|---|
| Sunflower | 50 | 7.5 s | 300 | 25 sun at age 6 s, then every 24 s |
| Peashooter | 100 | 7.5 s | 300 | 20 damage per pea, every 1.5 s |
| Wall-nut | 50 | 30 s | 4,000 | Blocks and absorbs bites |
| Cherry Bomb | 150 | 50 s | 300 | Fuse 1.2 s, 1,800 damage in a 3×3 area |
| Potato Mine | 25 | 30 s | 300 | Arms at 14 s, 1,800 damage to zombies in its tile |
| Snow Pea | 175 | 7.5 s | 300 | Pea damage plus 10 s of half-speed movement/bites |
| Chomper | 150 | 7.5 s | 300 | Eats one zombie including armor, digests 42 s |
| Repeater | 200 | 7.5 s | 300 | Two 20-damage peas 0.15 s apart; volley every 1.5 s |

Shooters fire at the next plant phase once ready and a living target is ahead in the same
lane. A Repeater's scheduled second pea fires even if its first pea killed the last target.
Removing the plant cancels its pending second shot. Projectiles already fired keep moving.
Shots move ten tiles/second and hit the nearest target crossed, breaking ties by entity ID.

Explosion columns use half-open tile bounds. A bomb at column 3 affects positions from
2.0 through just below 5.0 tiles in its row and the adjacent two rows. A mine affects only
its own row and tile. Bombs/mines disappear after exploding. An arming mine can be eaten.

Chomper targets the nearest living zombie from its center through one tile ahead, including
the endpoint. Digestion blocks further attacks. It consumes any shipped zombie, regardless
of armor, and can be bitten while digesting.

## Zombies and defense

| Zombie | Body HP | Armor | Speed, tiles/s |
|---|---:|---:|---:|
| Basic | 200 | 0 | 0.20 |
| Flag | 200 | 0 | 0.24 |
| Conehead | 200 | 400 | 0.20 |
| Buckethead | 200 | 1,100 | 0.20 |
| Pole Vaulting | 400 | 0 | 0.40 with pole, 0.20 after vault |

Damage consumes armor first and carries excess into body health. All zombies bite for
100 damage per second at a plant's contact boundary (0.3 tiles right of its center).
Bite progress starts on contact and resets when changing or losing the target.

Slow halves movement and bite progress. It does not stack; later ice hits refresh expiration.
Slow does not extend a vault animation. A pole zombie begins a 0.8-second vault at its first
blocking plant, then lands one tile left of that contact point and permanently loses its pole.
It is damageable during the vault. Removing the vaulted plant does not change the saved
landing position. Ready mines and Chompers resolve contact attacks before a new vault.

Each lane begins with a mower at x=0. It activates when a living zombie reaches that boundary,
sweeps right at five tiles/second, and is spent beyond the spawn boundary at x=9.5.
The sweep kills all touched zombies regardless of armor. It is not a permanent lane clear:
zombies spawned behind a moving mower or after it has passed can reach the house.
The house boundary is x=-0.5.

## Time and outcome

Simulation runs at 20 Hz. Rendering uses its own frame rate. Effects resolve in this order:
action, clock/cooldowns, spawn/sky income, plant behavior, projectiles, first death cleanup,
zombie behavior, mowers, final cleanup, outcome. Stable ID order breaks other ties.

Thus a zombie killed by a plant cannot bite that tick, and a mower may prevent a breach
on the same tick it activates. Defeat is checked after defense effects; victory requires
zero living and zero scheduled zombies. Empty gaps between waves are never victories.

There is no engine time limit. A custom unwinnable or zero-speed scenario can run forever;
the caller decides its own cutoff. Frames may be rendered less often, but no game ticks are
dropped. Entity state, not animation frames, determines collisions and effects.

## Level composition

Waves begin after 30 seconds, normally 25 seconds apart, with seeded within-wave jitter.
The total schedule is resolved once. Easy has 15 zombies in five waves; standard has 40 in
ten; hard has 75 in fifteen. Hard repeats standard's opening compositions and adds five
larger waves. Counts and compositions are fixed by the shipped configuration, while rows
and precise spawn ticks vary with seed.

This game automatically collects sun, exposes the remaining zombie count, has no seed-bank
selection or unlock campaign, and uses the explicit balance above. These differences are
part of the research environment and should be stated when reporting later experiments.
