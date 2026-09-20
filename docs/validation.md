# Release validation — 1.1.0

Date: 2026-09-20. Platform: Windows 11, Python 3.12.3, Intel Core i9-14900HX,
32 logical processors, approximately 32 GiB RAM. The simulation and tests use CPU execution;
the installed RTX 4070 Laptop GPU is not required.

## Automated checks

The release suite contains **126 passing tests**, including generated Hypothesis cases.

| Area | Verified behavior |
|---|---|
| Resources | Exact-cost success, one-sun-short failure, no charge on rejection, timed income, cap |
| Actions | Four board corners, invalid coordinates/types, occupied tiles, digging, shared cooldowns |
| Combat | Independent ten-hit calculation for 200 HP, armor overflow, nearest target, lane isolation |
| Special plants | Repeater's exact burst ticks, bomb boundaries, mine arming/eating, Chomper digestion |
| Special zombies | One vault only, removed vault target, slow refresh/expiry and half-rate bites |
| Collision counterexamples | Fast projectile crossing, zombie crossing a projectile, zombie crossing a moving mower |
| Outcomes | House breach, defense on the last tick, mower reuse prevention, no victory between waves |
| Counts | Concurrent spawning/death, conservation identities, no double-counted defeats |
| State isolation | Frozen observations, detached snapshots, independent games/RNGs, atomic invalid reset |
| Replay | Seed reproducibility, tick-batch equivalence, JSON restoration, tamper detection |
| Configuration | Explicit/generated scenarios, bounds, known types, positive timing and tick alignment |
| UI | Human input through the API, rejection feedback, pause/single step/restart/menu, draw purity |
| Replay annotations | Detached finite JSON, atomic rejection, metadata-independent hashes, cutoff timing and outcome precedence |
| Offscreen rendering | No window/input access, existing display preserved, fresh surfaces, RGB layout, scaling and clip restoration |

The movement counterexamples test both original successful cases and cases in which two
objects pass each other between tick samples. Fixes preserve the same collision boundaries;
they do not relax outcomes or resource rules.

Run:

```text
python -m pytest -q
ruff check src tests tools examples
python -m compileall -q src examples tools tests
```

## Winning playthroughs

These are fixed acceptance traces generated using legal public actions, the unmodified
shipped presets, and seed 42. No state edits, future-spawn inspection, extra starting sun,
or forced outcomes are used by the controller. Every trace is replayed and hash-verified.

| Level | Outcome | Final tick | Simulated duration | Defeated | Unused mowers |
|---|---|---:|---:|---:|---:|
| Easy | Won | 3,221 | 161.05 s | 15 / 15 | 2 |
| Standard | Won | 6,105 | 305.25 s | 40 / 40 | 3 |
| Hard | Won | 8,526 | 426.30 s | 75 / 75 | 2 |

For 1.1.0, regenerated traces under `artifacts/acceptance-v1.1.0/` match all three 1.0.0
fixtures exactly in final tick and hash. The engine, rules, preset configurations, and tracked
fixtures are unchanged. Expected SHA-256 final state hashes:

```text
easy     e812432b769a3306120978b90473f6279f93d643e3fdf700059252091bfd76a2
standard 6b0527497e60cd91f133bb16845c1719b1ddcdb23c0ee5463d80aef6cb698787
hard     dafb56ec0c459db34b011e31ccbab8ecd0cd9063f9caa85cb37e89ede8f780f6
```

The files are under `tests/fixtures/`. Regenerate intentionally with
`python tools/record_playthroughs.py`, and inspect any changed hashes before accepting them.
The verification controller was adjusted during playability work; it is not a benchmark
policy, a human-similarity experiment, or evidence of performance on held-out seeds.

## Performance

Measured for 1.1.0 with `python tools/benchmark_suite.py`, without concurrent test/build
workloads. Counts are simulation ticks; every tick
exports a full detached observation. They are not frame rates or learner decision rates.

| Workload | Ticks/s | Real-time multiple | Measurement |
|---|---:|---:|---|
| Standard preset, wait-only | 35,070.7 | 1,753.5× | 20,000 ticks; reset after completion |
| Populated hard winning replay | 10,610.1 | 530.5× | 25,578 ticks; includes replay decoding and checkpoint hashes |
| Crowded 200-zombie scenario | 1,160.6 | 58.0× | 4,000 ticks with 15 initial shooters; reset after completion |

The standard preset exceeds the 2,000-tick/s target. The synthetic crowded case does not;
it is outside the normal 75-total-zombie preset and documents scaling limits of the simple
entity-loop implementation. Results are local measurements, not portable guarantees.

Rendering a populated state into an SDL dummy surface measured 487.4 frames/s over 120
frames. This excludes real monitor presentation, driver synchronization, and input latency;
interactive play is capped at 60 FPS by default. Drawing did not change the game state hash.

The shared offscreen renderer produced 1000×600 RGB24 frames at 136.1 frames/s over 120
frames, including board/HUD drawing, scaling, and byte export. Both rendering measurements
use warmed font caches and exclude video encoding. A separate fresh-process test uses an
invalid SDL display driver and forbids window initialization/input calls, proving that
offscreen rendering does not require the dummy display used by the interactive benchmark.

## Installation and visual checks

- Built a wheel and source distribution with the packaged TOML data.
- Installed the wheel without dependencies in a clean Python 3.12 environment.
- Verified pygame is absent there, `pip check` passes, and reset/step/state export work.
- Ran the external-control example to a natural outcome without private imports.
- Rendered and visually inspected the menu and a scene showing all eight plants and five
  zombies. Checked the pause screen and corrected mower clipping at the lawn edge.
- The source distribution includes documentation, examples, fixtures, and test support.
- Exported and visually inspected a final frame labeled TRUNCATED, with its external reason.
  The verified engine status remains running, with an unchanged final simulation hash.
- Verified the separate research project uses its own installed engine copy. Its installation
  and original source pin remain unchanged; adoption of this release requires both to update.

Generated benchmark JSON and visual previews are local artifacts, excluded from source
control. The reproducible tests, scenario data, and intentional acceptance fixtures are tracked.

## Limits

Only Windows/Python 3.12.3 was exercised. Real cross-platform replay agreement is unverified.
Interactive behavior is checked through pygame event tests and rendered frames; a lengthy
human usability study has not been performed. There is no learning system or measured RL
performance in this release. Package 1.1.0 deliberately retains engine version 1.0.0 and schema
version 1, so existing 1.0.0 snapshots/replays remain compatible. Migration across incompatible
engine/schema versions is not provided. Replay annotations are caller-supplied and are not
authenticated by simulation hashes. Rendering requires the optional pygame-ce dependency.
