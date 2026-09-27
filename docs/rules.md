# Daytime rules — daytime-1.4

The game runs at 100 Hz on a five-row, nine-column lawn with automatic sun
collection. Supported PC mechanics, all production/combat values and explicit
reconstruction limits are defined in [the mechanics contract](math/pc-mechanics.md).
Configuration in `src/pvz_game/data/rules.toml` is authoritative.

| Plant | Cost | Health | Recharge counter |
|---|---:|---:|---:|
| Sunflower | 50 | 300 | 750 ticks |
| Peashooter | 100 | 300 | 750 ticks |
| Wall-nut | 50 | 4,000 | 3,000 ticks |
| Cherry bomb | 150 | 300 | 5,000 ticks |
| Potato mine | 25 | 300 | 3,000 ticks |
| Snow pea | 175 | 300 | 750 ticks |
| Chomper | 150 | 300 | 750 ticks |
| Repeater | 200 | 300 | 750 ticks |

Recharge completes one tick after its counter limit. Nut/mine initially use
2,000 and cherry 3,500; fast cards begin ready. Each tile holds one plant.
Digging refunds nothing and does not clear recharge. The sun cap is 9,990.

Explosions test a source-pixel circle against zombie body rectangles, including
tangency. Cherry radius is 115 pixels in its own and adjacent lanes; mine radius
is 60 pixels in its own lane. Chomper uses its configured forward attack interval
with the biting tolerance described in [collision mathematics](math/gait-and-geometry.md).
It ignores headless bodies and misses a pole carrier or vaulting zombie.
Scheduled shooter windups survive loss of a target, but removing the shooter
cancels its pending shot. Fired projectiles remain independent of their plant.

Each lane's mower starts at x=0 and can activate once. It sweeps right and is
spent beyond x=9.5. Headless bodies do not activate idle mowers. Zombies behind
a mower can still threaten the house at x=-0.5 if they retain their heads.

Collision uses source-pixel rectangles converted to fixed-point units. Planting
legality remains tile occupancy, while zombie interaction uses the attack
rectangle: ordinary contact needs at least 20 pixels of overlap. Walking is
resolved before the four-tick bite cadence (eight ticks while chilled), so a body
that has passed an attack interval keeps walking. Projectile rectangles require
positive overlap; exact edge tangency misses. Underground mines can be bitten;
rising and armed mines remain bite targets but take no bite damage. They retain their trigger and
blast rules. Idle mowers use the swept zombie interval, catching a body that
crosses their contact range between samples.

Effects resolve as action, clock/cooldowns, spawn/sky income, plant behavior,
projectiles, first body removal, zombie movement/decay/bites, mowers, final
cleanup, outcome. Sweeps prevent objects crossing between samples from missing
collisions. Stable position/entity order resolves combat ties (an intentional
approximation of the reference's plant iteration order). A neutralized
zombie cannot bite or breach; a visible body may remain after victory.

Levels keep their custom schedules: preparation 30 seconds, waves normally
25 seconds apart with seeded jitter. Easy contains 15 threats in five waves,
standard 40 in ten, and hard 75 in fifteen. Future identities and exact
spawn times are absent from public observations. There is no engine time limit;
research callers own cutoffs. Rendering may sample fewer frames but never
changes simulation ticks, actions or gameplay RNG.
