# Iteration history

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
