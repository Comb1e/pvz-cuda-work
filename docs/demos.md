# Operation demos — package 1.2.1

A demo stores the initial game state and timed operations, then reconstructs the game while
you watch. It follows the StarCraft II replay approach using Lawn Lab's own `.pvzdemo` format.
It contains no rendered frames, model, or video. The caller supplies the operations.

## Generate from parameters

```python
from pvz_game import Place
from pvz_game.demo import ScheduledAction, generate_demo

result = generate_demo(
    level="standard", seed=42,
    actions=[
        ScheduledAction(0, Place("sunflower", 2, 0)),
        ScheduledAction(200, Place("sunflower", 1, 0)),
    ],
    max_ticks=1200,
    output="demos/sample.pvzdemo",
    metadata={"title": "Sample demonstration"},
    live=False, speed=1,
)
print(result.path, result.outcome, result.final_hash)
```

`level` accepts the same preset names, `LevelSpec`, and `WaveSpec` values as `Game.reset`.
`rules` optionally supplies a `Rules` object. Defaults are standard, seed 42, no tick cutoff,
no window, speed 1, and no overwrite. `output` is required.

`actions` is a sequence of `ScheduledAction(tick, action)` using `Place`, `Dig`, and `Wait`.
Ticks must be nonnegative integers in strictly increasing order. Tick 0 is before the first
simulation tick; an operation at tick 200 happens after ten simulated seconds. Gaps contain
waits. Two operations cannot share a tick. Each operation is applied exactly once.

Malformed schedules fail before opening a window or creating output. An illegal gameplay
operation, such as planting on an occupied tile, is recorded, rejected normally, and followed
by the requested passage of time. It is not silently replaced by a different action.

Without `max_ticks`, generation continues until a natural win/loss, including after the last
supplied operation. A nonnegative `max_ticks` stops at that exact tick. Operations at or after
the cutoff are not applied. If the game remains running, the result is labeled `truncated`
with reason `max_ticks`; a natural win/loss takes precedence. Zero generates an initial-state
recording. Operations after a natural ending are not executed.

Use `live=True` to watch while generating. Live and headless modes record the same operations,
durations, events, and state hashes. With identical parameters and metadata they also produce
identical compressed bytes on the same Python/platform/compression implementation.

## Record an existing game loop

```python
from pvz_game import Game, Place, Wait
from pvz_game.demo import DemoCancelled, DemoSession

game = Game()
game.reset("standard", seed=42)

with DemoSession(game, output="demos/recorded.pvzdemo", live=True, speed=2) as demo:
    try:
        result = demo.step(Place("sunflower", 2, 0), ticks=200)
        result = demo.step(Wait(), ticks=200)
        summary = demo.finish(outcome="truncated", termination_reason="sample_end")
    except DemoCancelled:
        summary = demo.result

print(summary.outcome, summary.duration_seconds)
```

The game must already be reset. Recording can begin mid-game. While the session is active,
route every simulation step through `demo.step`; read `game.observe()` and
`game.legal_actions()` normally. `step` returns the standard `StepResult`, including all events
and the actual number of ticks advanced. It records one entry per submitted call, regardless
of how many frames are rendered. Malformed calls do not mutate the game or add an entry.

`finish(outcome=None, termination_reason=None)` verifies and atomically saves the recording,
closes its live window, and returns a frozen `DemoResult`. Calling it again returns the same
result. Stepping a finished session raises `RuntimeError`.

| DemoResult field | Meaning |
|---|---|
| `path` | Requested output path as a `Path` |
| `observation` | Detached final public observation; status remains the actual game status |
| `outcome` | Actual win/loss or external truncated/interrupted label |
| `ticks_recorded` | Final tick minus the recording's initial tick |
| `duration_seconds` | Recorded ticks divided by the simulation tick rate |
| `final_hash` | SHA-256 of final simulation state |

For a running game, `finish()` defaults to `interrupted` / `recording_stopped`. Explicit
external outcomes may be `truncated` or `interrupted`. Metadata uses the existing replay
conventions and remains outside game observations, snapshots, and simulation hashes.

The context manager saves completed operations on exit. A caller exception is re-raised
after saving with reason `caller_error`. Closing a live window finalizes completed ticks,
sets `interrupted` / `window_closed`, and raises `DemoCancelled` to a streaming caller.
`generate_demo` handles that exception and returns the interrupted result instead.

Both APIs protect existing files unless `overwrite=True` is supplied. Publishing uses a
temporary file beside the destination and an atomic replace or exclusive hard link. A file
created by another writer during generation is protected too. Exclusive publication requires
a filesystem supporting hard links; failures leave an existing destination untouched.
Successful saves leave no temporary files. Verification detects unrecorded direct game steps
before publishing a demo.

Live display is synchronous and pumps events during `step`. Pausing blocks further ticks
until resumed; single-step advances one tick while paused. The caller owns time between calls,
so long computations between calls can delay window input handling. Live mode needs the `ui`
extra and its own pygame display. Headless mode needs neither pygame nor a display.

## TOML and commands

```text
pvz demo --script examples/demo.toml --output demos/sample.pvzdemo
pvz demo --script examples/demo.toml --output demos/live.pvzdemo --live --speed 4
pvz replay demos/sample.pvzdemo --watch --speed 2
pvz replay demos/sample.pvzdemo
pvz replay demos/sample.pvzdemo --frame artifacts/final.png
python examples/record_demo.py --live
```

Add `--overwrite` to the generation command to intentionally replace an existing output.
`--speed` on `pvz replay` requires `--watch`. A minimal script:

```toml
[demo]
level = "standard"
seed = 42
max_ticks = 1200

[metadata]
title = "A short demonstration"

[[actions]]
tick = 0
kind = "place"
plant_type = "sunflower"
row = 2
col = 0
```

`[demo]` permits `level`, `scenario`, `rules`, `seed`, and `max_ticks`. Choose `level` or
`scenario`; the latter is a path to an existing scenario TOML. `rules` is a rules TOML path.
Resolve both paths relative to the script. `[metadata]` contains finite JSON-compatible
annotations. Each `[[actions]]` table has a tick and the existing action fields: `kind` is
`place`, `dig`, or `wait`; place requires plant type/row/column, dig requires row/column.
Unknown sections, settings, and malformed actions are rejected.

`load_demo_script(path)` returns keyword arguments for `generate_demo`, allowing the same
script to be used by Python callers. The CLI controls output, live mode, speed, and overwrite.

## Watch and seek

| Control | Behavior |
|---|---|
| Timeline drag | Seek; pause while dragging, then restore the previous playback mode |
| Space / Pause | Pause or resume |
| Period while paused | Advance one simulation tick |
| Left / Right | Seek five simulated seconds backward/forward |
| Home / End | Seek to the recording's initial/final tick |
| R / Restart | Return to the initial state and play |
| Speed button | Cycle 0.5×, 1×, 2×, 4×, 8× |
| I / Inspect | Toggle entity inspection |

The footer shows elapsed/total recording time and the latest placement/dig operation with
its absolute tick, zero-based coordinates, and acceptance/rejection. The timeline and speed
controls remain usable after completion. Seeking is available when watching saved demos;
live recording offers pause, single-step, speed, and inspection.

Python callers can use `Playback.start_tick`, `end_tick`, `current_tick`, and `seek(tick)`.
Seek uses absolute simulation ticks, including when the recording starts mid-game. It returns
the target observation and preserves `Playback.game` identity. Invalid targets fail before
mutation. `seek_steps(tick)` returns an iterator yielding each simulated step for responsive
controllers; the UI consumes bounded chunks. `last_operation` is a frozen `RecordedOperation`
with `tick`, `action`, and its `ActionResult`, or None before any placement/digging operation.

Checkpoints store game state, replay cursor, and latest operation in memory every 200 ticks.
The initial checkpoint is always retained, with at most 64 additional checkpoints. Seeking
restores the nearest usable checkpoint and executes remaining operations, including targets
inside multi-tick entries. Rewinding clears completion labels and stale effects. Hash mismatches
raise errors; discard a playback object after failed verification.

Speeds, checkpoint intervals, cache limits, seek chunk sizes, and recording/generation batch
defaults live in `src/pvz_game/data/demo.toml`. Speed affects wall-clock pacing only. Rendering
may occur less frequently than ticks; the simulation never skips operations or physics ticks.

## Format and compatibility

`.pvzdemo` is gzip-compressed replay JSON with a zero timestamp in its gzip header. `.json`
remains uncompressed, and `.json.gz` is also accepted for compressed output. Readers detect
gzip by its header. The payload retains replay schema version 1: initial complete state,
resolved configuration, timed actions, checkpoint hashes, final state hash/status, and
optional metadata. It contains privileged debugging data, including future spawns, and is
not a policy observation. Seek caches and rendered frames are never written to the file.

Package 1.2.1 retains simulation compatibility version 1.0.0. Existing JSON replays and
snapshots remain valid. Readers from before 1.2.0 need the demo decompressed to JSON or an upgrade to
read compressed files. Source-pinned consumers adopt the new installation and source pin
together. The format is specific to Lawn Lab and cannot be opened by StarCraft II.
