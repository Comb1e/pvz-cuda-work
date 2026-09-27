# 100 Hz release verification — 2026-09-23

## 1.7.0 collision audit — 2026-09-27

Package 1.7.0 uses simulation compatibility 1.4.0. The independent CPU audit
controls pass for positive 20-pixel attack overlap, one-unit boundary misses,
projectile tangency, mine bite phases, custom one/two-HP lethal accounting and
idle-mower crossings. The CUDA kernel compiled and its available differential
cases passed; old 1.6.0 fixture snapshots intentionally require their original
engine. No formal learning run was launched.

Package **1.4.0**, simulation **1.1.0**, pinned rule clock **100 ticks/second**.
Complete game regression suite: **224 passed in 192.30 s** on the RTX 4070 laptop,
using the existing research environment. Cache, bytecode, and temporary results
were directed to the research artifacts directory, outside this checkout.

The suite includes every plant/zombie mechanic, ordered CPU/CUDA snapshots and
hashes, storage boundaries, resets, immediate actions, renderer purity, playback
seeking and completion/rewind. New independent controls assert physical movement,
shot intervals, preparation/production times and rejection of the old simulation
version. Three replay fixtures retain victories: easy 16108 ticks, standard 30529,
hard 42843. Tick rounding changes collision/attack timing, so old hashes and exact
terminal tick values are intentionally incompatible. Sources still define durations
in seconds and movement in units/second.

The research integration separately verifies its timer-free observations, reward
adapter and policy history. No formal training was launched for this game release.

## Historical results

# Native research replay verification — 2026-09-21

- Complete game suite: **222 passed in 41.48 seconds**. Cache, bytecode and
  temporary test output were directed outside this checkout.
- New fixtures cover compressed/plain input, same-tick placement and digging,
  batched waits, mid-game starts, cache boundaries, completion and rewind,
  instant-only recordings, natural win/loss over external cutoff, unknown format,
  corrupted hashes/timeline and native headless viewer rendering.
- The completed SC2 checkpoint's original demos verify without conversion:
  easy won at 4226, standard lost at 4184, hard lost at 5074. Final hashes match
  the research manifests; rewind followed by seeking to completion matches again.
- Source launcher verification succeeded using the research environment's Python;
  that environment still imports its original pinned simulator outside the launcher.
- The native easy-demo final frame was visually inspected. No simulation state,
  recording file, game rules or recorded tick count changed.

Research logs: `E:/Projects/Tower-Defence-AI/PVZ-plant/artifacts/` contains the
complete native and CUDA suite logs, launcher verification JSON and the final frame.
No formal training was started by these replay checks.

---

# CUDA release verification — 1.3.0

2026-09-21, Windows, Python 3.12, RTX 4070 Laptop, CUDA PyTorch 2.8.0+cu128,
CuPy 13.6.0, NVRTC 12.8.93 and runtime 12.8.90.

- Complete game suite: **214 passed in 51.41 s**.
- 15 CUDA cases include all plants/zombies, integer movement and timers, action
  masks/acceptance, ordered public events, exact canonical snapshot hashes,
  preserved archived easy/standard/hard wins and failures, simultaneous crowded
  mower contacts, mid-game shots, resets and transactional capacity rejection.
- Research-side independent checks additionally compare encoders, reward
  components, device GAE, losses, gradients and optimizer updates to CPU/SB3.
- The optional runtime compiles and executes kernels on Windows without `nvcc`
  or a machine-wide toolkit. DLPack pointer identity and shared-stream writes
  are verified by the research `doctor` probe.

The first full-suite invocation used a nonexistent parent for pytest's external
temporary directory; its 65 fixture setup errors were corrected by creating the
external parent, then the entire suite passed. No game assertion was loosened.
Original user checkouts/environments/jobs are untouched; development and caches
use isolated worktrees or external directories. See the consumer's
`docs/gpu-performance.md` for bounded whole-training measurements.

## Earlier verification records

# Release validation — 1.2.1

Date: 2026-09-20. Platform: Windows 11, Python 3.12.3, Intel Core i9-14900HX,
32 logical processors, approximately 32 GiB RAM. The simulation and tests use CPU execution;
the installed RTX 4070 Laptop GPU is not required.

## Automated checks

The 1.2.0 full release suite passed **199 tests**, including generated Hypothesis cases.
Patch 1.2.1 reran **77 relevant rendering, UI, demo, property, and replay tests**, all passing.
Direct rendering checks verified `0/15`, `2/15`, `15/15`, `0/0`, `75/75`, and `200/200`,
sidebar fit, and unchanged simulation state. The `2/15` and `200/200` frames were visually
inspected. The performance measurements below remain explicitly those from 1.2.0.

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
| Demo generation | Streaming/prepared inputs, mid-game starts, exact cutoffs, default interruption, natural outcome precedence, malformed schedule rejection |
| Compact files | JSON/gzip equivalence, deterministic bytes, incomplete/corrupt files, overwrite protection, concurrent destination creation, no leftover temporary files |
| Live recording | Identical step results/events/entries/bytes at all five speeds; pause, single step, cancellation before and inside calls, caller errors |
| Replay seeking | Linear-reference equivalence, generated seek sequences, entry boundaries, mid-entry targets, cache eviction, game identity, tamper detection |
| Viewer transport | Bounded seeks, timeline dragging, seek after completion, shortcuts, operation feedback, speed transitions back to human play |

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

For 1.2.0, regenerated traces under `artifacts/acceptance-v1.2.0/` match all three 1.0.0
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

Measured for 1.2.0 with `python tools/benchmark_suite.py`, without concurrent test/build
workloads. Counts are simulation ticks; every tick
exports a full detached observation. They are not frame rates or learner decision rates.

| Workload | Ticks/s | Real-time multiple | Measurement |
|---|---:|---:|---|
| Standard preset, wait-only | 33,198.8 | 1,659.9× | 20,000 ticks; reset after completion |
| Populated hard winning replay | 7,614.0 | 380.7× | 25,578 ticks; includes decoding, hash checks, and seek-cache maintenance |
| Crowded 200-zombie scenario | 1,085.8 | 54.3× | 4,000 ticks with 15 initial shooters; reset after completion |

The standard preset exceeds the 2,000-tick/s target. The synthetic crowded case does not;
it is outside the normal 75-total-zombie preset and documents scaling limits of the simple
entity-loop implementation. Results are local measurements, not portable guarantees.

Rendering a populated state into an SDL dummy surface measured 514.1 frames/s over 120
frames. This excludes real monitor presentation, driver synchronization, and input latency;
interactive play is capped at 60 FPS by default. Drawing did not change the game state hash.

The shared offscreen renderer produced 1000×600 RGB24 frames at 143.8 frames/s over 120
frames, including board/HUD drawing, scaling, and byte export. Both rendering measurements
use warmed font caches and exclude video encoding. A separate fresh-process test uses an
invalid SDL display driver and forbids window initialization/input calls, proving that
offscreen rendering does not require the dummy display used by the interactive benchmark.

## Demo size and seeking

Measured with `python tools/benchmark_demos.py`. Each demo is generated from the original
winning trace's supplied operations, using the same preset/seed and normal public actions.
All final hashes and winning ticks match the table above. The generator verifies before
publishing; the seek measurements also execute checksum checks.

| Demo | Compressed bytes | Equivalent JSON bytes | Generation + verification | Cold seek to end | Cached seek mean / max |
|---|---:|---:|---:|---:|---:|
| Easy | 6,023 | 27,232 | 0.298 s | 0.274 s | 9.5 / 22.6 ms |
| Standard | 7,383 | 44,350 | 0.844 s | 0.828 s | 14.3 / 34.5 ms |
| Hard | 8,497 | 59,447 | 1.390 s | 1.273 s | 18.8 / 44.4 ms |

Cached measurements use 100 reproducible target ticks after the initial full traversal.
The in-memory cache is limited to the initial snapshot plus 64 entries. Timing includes
snapshot restoration and re-simulation, not input latency or display presentation. No seek
snapshots or rendered frames are added to demo files. Populated replay now maintains this
cache, so its workload includes more work than the 1.1.0 replay benchmark.

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
- Generated a compact sample through the TOML CLI, verified it, and exported its final frame.
- Rendered and visually inspected live, seeking, playback, and completed demo transport screens
  with `python tools/preview_demos.py`; the timeline remains visible and usable after completion.

Generated benchmark JSON and visual previews are local artifacts, excluded from source
control. The reproducible tests, scenario data, and intentional acceptance fixtures are tracked.

## Limits

Only Windows/Python 3.12.3 was exercised. Real cross-platform replay agreement is unverified.
Interactive behavior is checked through pygame event tests and rendered frames; a lengthy
human usability study has not been performed. There is no learning system or measured RL
performance in this release. Package 1.2.1 deliberately retains engine version 1.0.0 and schema
version 1, so existing 1.0.0/1.1.0 snapshots/replays remain compatible. Migration across incompatible
engine/schema versions is not provided. Replay annotations are caller-supplied and are not
authenticated by simulation hashes. Rendering requires the optional pygame-ce dependency.


## 1.5.0 verification — 2026-09-25

The maintained suite contains 226 tests. The full pass completed 225 tests; the
remaining crowd boundary control still assumed the old movement speed. Its
independent expected crossings are 60 neutralizations on tick one (flag/pole
lanes) and 150 on tick two; that corrected control passed separately. CPU/CUDA
comparisons cover all eight plants, five zombie types, public events, complete
snapshots, hashes, gameplay RNG continuation, headless decay and mixed resets.
Ruff passes. No learning run was launched.

The public-observation acceptance controller wins easy, standard and hard at
ticks 14,788 / 29,334 / 43,454, respectively, with five mowers still ready.
Their regenerated acceptance recordings replay exactly. These are game
correctness controls, not agent performance results. See the mechanics
derivation for the retained animation-free movement and collision limits.


## 1.6.0 verification — 2026-09-26

Independent rational gait integration, half-rate phase progression, contact and
blast boundary controls were written before or alongside the behavior changes.
The CPU suite passes 227 tests. CUDA differential controls pass all 17 cases
(including every supported plant, event order, RNG, snapshots, headless decay,
strict mower contacts and the new replay fixtures). Targeted post-audit mower
checks are included in the final run. Source imports were explicitly pointed
at this checkout so tests did not accidentally exercise the installed 1.5.0.

Fresh public-API seed-42 acceptance controllers win easy/standard/hard at
14936/29352/42381 ticks, retaining five ready mowers, and verify their replays.
New files are under `tests/fixtures/v16/`; previous fixtures remain unchanged.
The research saving controls passed all 50 lane/mode combinations without lesson
retuning. These are controlled witnesses and failure cases, not PPO/Q-learning
experiments or original-executable equivalence evidence.
