# Iteration history

## 1.3.0 — 2026-09-21

### Previous issue and root cause

Research collection simulated Python entity objects and transferred observations,
actions and masks between CPU workers and the GPU. The CPU/IPC path limited the
number of parallel games usable by the laptop GPU.

### Improvements

- Optional CuPy 13.6/NVRTC backend with contiguous integer state and independent
  CUDA games. Preserve operation order, targeting ties, remainders and IDs.
- Checked batched scenario reset/restore, 406-action masks, immediate action
  phases, compact combat facts, and diagnostic events/snapshots/hashes.
- Proved projectile storage bound; reject insufficient roster/shot capacity
  before mutation. Modified rules stay on the explicit Python backend.
- Optional Windows runtime/header/compiler wheels; ordinary gameplay/replays
  retain the dependency-free Python engine and native renderer.

### Verification and remaining limits

Complete game suite: **214 passed in 51.41 s**, including 15 CUDA differential
cases. Replayed the easy/standard/hard seed-42 archived action streams, matching
intermediate and final hashes, ticks, events and outcomes. Tested every plant
against every zombie type, crowded mower sweeps, mid-game projectile restore,
legality/acceptance, same-tick placement/digging, resets and capacity rejection.
The simulation compatibility identifier remains **1.0.0**; package is **1.3.0**.

CUDA executes ordered combat within each game. Further intra-game parallelism
would need new race/order proofs. Signed int64 storage and declared capacities
are explicit limits. GPU speed is measured by the consumer's complete training
pipeline; this release makes no learning-quality or hardware speedup claim.

## 1.2.1 — 2026-09-20

### Previous issue and root cause

The main zombie counter displayed only the remaining number. Although observations already
provided defeated and initial-total counts, the HUD did not express progress as requested.

### Improvements

- The shared HUD now shows defeated/total, for example `2/15`, in gameplay, live previews,
  replays, and exported frames. The denominator includes every scheduled zombie in the level.
- Kept remaining, on-lawn, and upcoming subtotals. The counter chooses a smaller existing
  font when necessary to fit larger custom scenarios into the sidebar.
- Documented the format while retaining separate integer API fields and simulation version 1.0.0.

### Verification and remaining limits

Checked initial, partial, complete, empty, and large counts (`0/15`, `2/15`, `15/15`, `0/0`,
`75/75`, `200/200`), including visual layout and unchanged simulation hashes. Existing rendering,
UI, live demo, property, and replay checks cover the shared paths. This is a presentation change;
77 targeted tests pass. Existing platform, synchronous live-preview, and source-pin limitations
still apply.

## 1.2.0 — 2026-09-20

### Previous state and issues

External callers could record and render games, but each caller had to build its own demo
generation loop. Recordings were plain JSON. Watching supported forward playback only;
there was no timeline, exact-tick seek, or live preview of externally submitted operations.

### Root causes

- Replay serialization did not provide compressed, atomic demo publication.
- Batched recorder calls had no intermediate presentation hooks or partial-call finalization.
- Playback did not preserve restorable cursors for navigating inside recorded operations.
- Interactive controls and completion modals were designed around forward-only playback.

### Improvements

- Added parameterized `generate_demo`, `ScheduledAction`, streaming `DemoSession`, frozen
  `DemoResult`, and a TOML-driven `pvz demo` command. Operations remain caller-supplied.
- Added gzip `.pvzdemo` files with deterministic headers, atomic publication, and explicit
  overwrite protection. Existing JSON, verification, and frame export remain supported.
- Added optional live preview with pause, single tick, inspection, and configurable speeds.
  A partial cancelled call records only completed ticks, and caller exceptions preserve the
  completed recording. One submitted call remains one entry at every rendering speed.
- Added exact-tick seeking with bounded in-memory caches and incremental UI work. Restoring
  a cursor preserves Game identity and latest operation feedback; rewinding clears stale effects.
- Added a timeline, seek shortcuts, and 0.5x/1x/2x/4x/8x playback. Ended demos remain seekable.
- Kept human speed controls valid when returning from a demo using 0.5x or 8x speed.
- Added examples, demo documentation, benchmark/preview tools, and an inspected SC2 protocol
  reference. Engine compatibility remains 1.0.0, with replay/snapshot schemas at version 1.

### Verification results

- 199 tests pass, including original mechanics, generated seek sequences, live/headless event
  and byte equality at every speed, cancellation before/during a call, cutoff boundaries,
  malformed inputs, corruption, output races, timeline navigation, and core import isolation.
- All three baseline playthroughs regenerate with the original hashes and winning ticks.
  Generating compact demos from their operations also reproduces those outcomes exactly.
- Compact winning demos occupy 6,023 / 7,383 / 8,497 bytes for easy/standard/hard. Cached
  seeks average 9.5 / 14.3 / 18.8 ms over 100 targets in each recording.
- Standard full-API simulation reaches 33,198.8 ticks/s; populated replay including seek-cache
  maintenance reaches 7,614.0 ticks/s. See `validation.md` for complete measurements.
- Live, seeking, playback, and completed replay views were rendered and visually inspected.

### Remaining issues and intentional limits

- Live streaming preview processes input during `step`; lengthy caller work between calls can
  delay window input. No background simulation or policy/model integration is introduced.
- Demo files use Lawn Lab's own format. They are not SC2-native files or video exports.
- Exclusive atomic publication requires hard-link support on the destination filesystem.
- Large/long recordings still require initial replay execution to build useful seek caches.
  Memory is bounded, so distant seeks can need additional re-simulation after cache eviction.
- Cross-platform pixel identity and cross-platform replay execution remain unverified.

## 1.1.0 — 2026-09-20

### Previous state and issues

Raw replays did not identify a controller checkpoint or explain why an external research
wrapper stopped a still-running game. External video tools had to provide their own board
and HUD drawing to avoid the interactive application's display window.

### Root causes

- Replay records described simulation state only; external cutoff/provenance annotations
  had no documented place in the file.
- Board and HUD drawing lived inside the interactive controller and read its input state.

### Improvements

- Added optional detached JSON metadata to Recorder and Playback, with atomic updates and
  conventional policy/checkpoint/outcome/reason fields. Simulation hashes exclude metadata.
- Added explicit outcome resolution: real wins/losses take precedence; external truncation
  or interruption applies only after playback reaches its verified end.
- Extracted original art and one board/HUD renderer shared by interactive and offscreen use.
  Offscreen output supports fresh Surfaces, RGB24 bytes, and aspect-preserving output sizes.
- Added explicit context/options instead of reading input devices while drawing. Moved the
  common palette and labels into TOML. Kept legacy art imports working.
- Added verified replay frame export, a standalone offscreen example, and a source pin tool.
- Kept engine compatibility version 1.0.0 and schema version 1; package release is 1.1.0.

### Verification results

- 126 tests pass, including existing action/legality/observation tests and new metadata,
  cutoff precedence, malformed JSON, display isolation, RGB layout, and clipping checks.
- Regenerated all three seed-42 acceptance runs outside the fixtures: winning ticks and
  full state hashes match 1.0.0 exactly. No engine, balance, level, or fixture edits.
- Offscreen rendering works in a fresh process with an invalid display driver and fails
  the test if it calls display initialization, window creation, or input access.
- Interactive and truncated offscreen frames were rendered and visually inspected.

See `validation.md` for installation checks and current performance measurements.

### Remaining issues and intentional limits

- Metadata is caller-supplied; simulation hashes do not authenticate provenance or verify
  checkpoint files. External manifests can hash the complete recording.
- Rendering still requires the optional pygame-ce extra. There is no bundled video encoder;
  external tools can feed the RGB24 bytes to their encoder of choice.
- Fonts can differ across platforms; pixel identity across machines is not guaranteed.
- Source-pinned research consumers must update their installation and manifest together.
  Existing research installations are unchanged by this package release.

## 1.0.0 — 2026-09-20

### Previous state and issues

The project folder was empty, with no game, control API, tests, documentation, or Git history.
There was no earlier released game version. During implementation, collision checks needed
to handle moving objects crossing between ticks; equal-size opening waves also overwhelmed
the starting economy before meaningful planting choices could develop.

### Root causes

- Sampling only final positions misses opposing motion across a projectile or mower boundary.
- Counting defeats as a population decrease mixes spawning and deaths in the same update.
- Front-loading the full wave size gives too little economy-building time at 50 starting sun.
- A display-owned game clock would make replay and headless execution depend on frame rate.
- Loosely restored entity values can break later updates even if a snapshot's version matches.

### Improvements

- Added one deterministic 20 Hz simulation shared by human input, external callers, and replay.
- Implemented all eight agreed plants, all five zombies, automatic sun, mowers, and outcomes.
- Added integer timers, fixed-point positions, retained movement remainders, and explicit states.
- Added swept collisions including movement of zombies against projectiles and mowers.
- Added explicit damage/defeat events and checked zombie-count conservation.
- Ramped wave compositions while preserving 5/10/15 waves and 15/40/75 zombies. Hard uses the
  standard opening followed by five larger waves. Rules remain at the planned balance values.
- Added immutable observations, one legality validator, custom explicit/generated scenarios,
  atomic snapshot restoration, version checks, and hash-verified replays.
- Added a pygame-ce interface with original drawings, inspection, pause, speed, and recording.
- Added packaging with optional UI dependencies, CLI commands, examples, source references,
  and current architecture/data-flow/state diagrams.

### Verification results

- 87 tests pass, including independent damage/income calculations, boundary/counterexample
  collisions, property-based invariants, snapshot corruption checks, and UI control tests.
- All shipped seed-42 scenarios have winning traces; complete replay hashes match.
- Standard wait-only execution: 35,626.7 ticks/s. Populated hard replay: 11,113.3 ticks/s.
- Crowded 200-zombie scenario: 1,045.0 ticks/s; this stress limit is explicitly documented.
- Clean core-only wheel installation passes dependency checks and runs without pygame.
- Menu, gameplay, and pause views rendered successfully; menu and gameplay were visually checked.

See `validation.md` for measurements, test categories, and reproducible commands.

### Remaining issues and intentional limits

- No night/pool/roof content, campaign unlocks, seed selection, audio, or original-game assets.
- Rules are a versioned PvZ-style preset, not an exact original-game simulation.
- Large simultaneous crowds cost more CPU; no spatial indexing or compiled engine is included.
- Cross-platform determinism and extended human usability have not yet been tested.
- Snapshots/replays reject incompatible versions; no migration support is provided.
- RL, reward design, observation tensors, training, and generalization studies remain external.
