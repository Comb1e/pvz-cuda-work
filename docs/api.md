# Python control API — version 1

Install `pvz-research-game` into the calling environment. The import name is `pvz_game`.
The core requires Python 3.12+ and no third-party runtime package.

Package release `1.2.1` presents zombie progress as defeated/total. `PACKAGE_VERSION` identifies
the package release; `ENGINE_VERSION = "1.0.0"` identifies compatible simulation state.
Observation, snapshot, and replay schemas remain version 1. Existing hashes remain valid.

See [the demo interface](demos.md) for `DemoSession`, parameterized `generate_demo`, TOML
scripts, compressed recordings, and the replay timeline. The game lifecycle below is unchanged.

## Game lifecycle

```python
from pvz_game import Game, Place, Dig, Wait, Status

game = Game()                       # Or Game(rules=Rules.from_toml("rules.toml"))
observation = game.reset("standard", seed=42)
result = game.step(Place("sunflower", 2, 0), ticks=4)
result = game.step(Wait(), ticks=20)
result = game.step(Dig(2, 0))
```

| Method | Contract |
|---|---|
| `reset(level="standard", seed=42)` | Start a preset, `LevelSpec`, or `WaveSpec`; return `Observation` |
| `step(action=Wait(), *, ticks=1)` | Apply one action, advance requested ticks, stop early on completion |
| `observe()` | Return a detached, immutable observation without advancing time |
| `validate_action(action)` | Return acceptance and rejection reason without advancing time |
| `legal_actions()` | Return every legal action in deterministic order |
| `snapshot()` | Return complete detached internal state, including future spawns |
| `restore(snapshot)` | Atomically restore a compatible snapshot and return observation |
| `state_hash()` | SHA-256 of canonical complete state, for repeatability checks |

Call reset before other methods. `step` after victory/defeat raises `GameFinishedError`.
An empty scenario starts running and wins on its first tick. There is no implicit time limit.
One `Game` instance is owned by one caller; use separate instances/processes for parallel runs.

## Actions and errors

`Place(plant_type, row, col)` and `Dig(row, col)` use zero-based board coordinates.
Rows are 0–4; columns are 0–8. Plant identifiers, in card order:

```text
sunflower, peashooter, wall_nut, cherry_bomb,
potato_mine, snow_pea, chomper, repeater
```

An illegal gameplay action is rejected, then the requested ticks still run. The action
does not spend sun or start recharge. Natural resource production and existing timers
continue during those ticks. Reasons: `outside_board`, `unknown_plant`, `occupied_tile`,
`card_recharging`, `insufficient_sun`, `empty_tile`. Validation after completion returns
`game_finished`, and legal actions are empty.

Malformed action types/coordinates raise `TypeError`. Nonpositive or noninteger tick
counts raise `ValueError`. These errors occur before mutation. Invalid reset configuration
also preserves an existing game. Boolean values do not count as integer coordinates/ticks.

`Wait()` is always legal while running. Legality is evaluated before the first requested
tick; sun produced or cooldowns completing during that tick become usable by the next action.

## Step results

`StepResult` is frozen and contains `observation`, `action_result`, `events`, `status`,
and `ticks_advanced`. Status is `Status.RUNNING`, `Status.WON`, or `Status.LOST`.
There is deliberately no reward, tensor encoding, or framework-specific termination tuple.

`game.step(action, ticks=4)` means a controller decision every 0.2 simulated seconds.
The same action is not repeated on the other three ticks. Calling the action once and then
three single-tick waits produces the same complete state.

## Public observation

| Field | Meaning |
|---|---|
| `api_version` | Observation schema version, currently 1 |
| `tick`, `elapsed_seconds`, `tick_rate` | Integer time, derived seconds, and 20 ticks/second |
| `units_per_tile`, `rows`, `cols` | Fixed-point scale (default 1000), board shape |
| `level`, `status`, `sun` | Current level identity, outcome, and available sun |
| `cards` | Type, cost, remaining cooldown ticks, full recharge ticks |
| `plants` | ID, type, row/column, health/max health, behavior state, timer |
| `zombies` | ID, type, row/x, body health, armor, behavior, slow timer, pole, behavior timer |
| `projectiles` | ID, row/x, damage, icy flag |
| `mowers` | Row, x, ready/moving/spent state |
| `wave`, `total_waves` | Current highest spawned wave and total waves |
| `counts` | Initial total, spawned, alive, defeated, not yet spawned, remaining |

The shared display formats zombie progress as
`f"{observation.counts.defeated}/{observation.counts.initial_total}"`, for example `2/15`.
The denominator is the fixed total for the full level, including future spawns. The API
continues exposing separate integer counts for calculation and external controllers.

Collections are tuples with stable entity IDs. Positions `x` use fixed-point units,
not pixels. A tile's center is `(column + 0.5) * units_per_tile`.

Plant timers are time to the next scheduled production, attack, arming, detonation, or
digestion completion; zero means ready. A zombie behavior timer gives remaining vault
ticks or ticks to the next bite at its current slow rate. Slow ticks are separately exposed.

Counts satisfy both identities after every step:

```text
remaining = alive + not_yet_spawned
initial_total = defeated + alive + not_yet_spawned
```

Future identities, positions, and exact spawn times are not in observations. Exact current
health and behavior timers are structured game state, not an approximation extracted from
pixels; the inspection UI also exposes those values.

## Events

`Event(kind, tick, entity_id, details)` is immutable. `details` is a tuple of key/value pairs;
use `event.get("amount")` or `dict(event.details)`. Events retain actual simulation ticks
when returned by a multi-tick step.

Kinds include `PlantPlaced`, `PlantRemoved`, `SunProduced`, `ZombieSpawned`, `DamageApplied`,
`ZombieDefeated`, `ProjectileFired`, `SlowApplied`, `MineArmed`, `PlantExploded`,
`ZombieSwallowed`, `PlantDamaged`, `VaultStarted`, `VaultFinished`, `MowerActivated`,
`MowerSpent`, `ActionRejected`, and `GameEnded`.

`SunProduced.amount` is credited sun after applying the cap; `produced` is the nominal
amount. Zombie damage splits `health_damage` and `armor_damage`. Damage `source` is the
responsible entity ID; mower sources are negative values `-row-1` because mowers are lane
equipment rather than numbered entities. Defeats are explicit events, never population deltas.

## Custom scenarios

```python
from pvz_game import InitialPlant, LevelSpec, Spawn, WaveSpec, load_scenario

explicit = LevelSpec(
    name="armor-test",
    spawns=(Spawn(tick=600, zombie_type="buckethead", row=2),),
    initial_sun=200,
    plants=(InitialPlant("sunflower", row=2, col=0),),
    mowers=False,
)
generated = WaveSpec(
    name="mixed-waves",
    waves=(("basic",), ("conehead", "flag")),
    preparation_seconds=30,
    wave_seconds=25,
    jitter_seconds=4,
)
game.reset(explicit, seed=42)
game.reset(generated, seed=42)
game.reset(load_scenario("examples/waves.toml"), seed=42)
```

Spawn ticks must be positive. Optional `Spawn.x` uses fixed-point units and defaults to
the configured spawn boundary. Generated waves must be nonempty, use known zombie types,
and have jitter shorter than wave spacing. Timing values must align exactly to 0.05 seconds.
Lanes are uniform random choices; jitter is an inclusive integer range from zero to the
configured maximum. No adaptation occurs during play.

## Snapshots and replay

Snapshots include rules, their hash, the resolved scenario, RNG state, all entities and
timers, counters, and outcome. `json.dumps`/`json.loads` round trips are supported. A snapshot
is an explicit privileged debugging export; do not use it as a policy observation by accident.

Restore requires snapshot version 1, engine version 1.0.0, and identical rules. It validates
entity/count invariants in a candidate instance before replacing the current game. Snapshot
formats are versioned and are not a general-purpose save editor.

```python
from pvz_game.replay import Recorder, Playback, verify_replay

recorder = Recorder(game)
recorder.step(Wait(), ticks=20)       # Use this instead of calling game.step directly.
recorder.save("recordings/session.json")
verified_game = verify_replay("recordings/session.json")
```

Recordings embed an initial snapshot, tick-indexed actions and durations, periodic hashes,
and a final hash/outcome. They can begin mid-game. Verification reconstructs and advances
the recording one tick at a time, checking every checkpoint. Incompatible versions or
changed action/state data raise an error rather than silently accepting divergent playback.

### Optional replay metadata and provenance

```python
recorder = Recorder(game, metadata={
    "policy_id": "shared-policy-v2",
    "checkpoint_sha256": "a" * 64,  # Supply the actual file hash in real experiments.
    "experiment": {"run_id": "run-003", "evaluation": True},
})
recorder.step(Wait(), ticks=20)
# The external wrapper, rather than the game, decides when its time limit is reached.
recorder.update_metadata({"outcome": "truncated", "termination_reason": "time_limit"})
recorder.save("recordings/limited.json")

playback = Playback("recordings/limited.json")
verified_game = playback.verify()
print(verified_game.observe().status)  # running, if the game itself has not ended
print(playback.display_outcome)       # truncated
print(playback.metadata["policy_id"])
```

Metadata is an optional top-level JSON object, separate from snapshots, observations, actions,
and simulation hashes. Omitting it preserves the previous replay shape. Nested dictionaries
and lists of finite JSON values are accepted, with string object keys. Inputs, exports, and
the `metadata` properties are detached copies; `update_metadata` merges top-level fields only.
Invalid updates leave existing annotations intact. The engine does not read metadata.

Use these field names as the shared provenance convention:

| Field | Meaning |
|---|---|
| `policy_id` | Caller-supplied name or stable identifier of the controller/checkpoint |
| `checkpoint_sha256` | Caller-supplied checksum of the checkpoint file |
| `outcome` | `running`, `won`, `lost`, `truncated`, or `interrupted` |
| `termination_reason` | Why the external controller stopped, such as `time_limit` |
| Other JSON fields | Application-owned annotations, for example a nested `experiment` object |

The four conventional fields must be strings when present. The checkpoint string is stored
verbatim; the engine does not open checkpoint paths or verify model files. Hash verification
authenticates simulation consistency only, not the truth of these caller-supplied annotations.
Use a whole-replay file checksum in an external manifest when metadata integrity matters.

`Playback.display_outcome` uses external cutoff labels only after verification reaches the
recorded end. Actual game wins/losses always take precedence. An external `won` label cannot
turn a still-running game into a victory. Legacy recordings without metadata keep their
original behavior. The CLI preserves `status` as the engine status and adds `outcome` and
`metadata` only when annotations exist.

### Offscreen board and HUD

Install the optional `ui` extra for pygame-ce. No display driver, window, event queue, or
NumPy dependency is needed by the offscreen renderer:

```python
from pvz_game.rendering import BoardRenderer, RenderContext

renderer = BoardRenderer(size=(1000, 600))
surface = renderer.render(game.observe())
rgb = renderer.rgb_frame(game.observe())
assert len(rgb.data) == rgb.width * rgb.height * 3

# For a completed replay's presentation, explicitly attach external labels.
surface = renderer.render(playback.game.observe(), context=RenderContext(
    policy_id=playback.metadata.get("policy_id"),
    outcome=playback.display_outcome,
    termination_reason=playback.metadata.get("termination_reason"),
))
```

`render` returns an independent pygame Surface. `rgb_frame` returns a frozen `RGBFrame` with
`width`, `height`, and packed `data`: RGB24, top row first, row-major, no padding. FFmpeg can
consume the bytes directly. In a project that already uses NumPy, convert with
`np.frombuffer(rgb.data, dtype=np.uint8).reshape(rgb.height, rgb.width, 3)`; call `.copy()` if
you need writable pixels.

The native canvas is 1280×820 by default. Requested output sizes preserve its aspect ratio
with background-colored letterboxing. `draw(observation, surface, ...)` paints into a
caller-owned native-size surface and restores that surface's clip rectangle. Rendering
initializes only pygame's font subsystem; it neither opens nor closes an existing display.
Images depend on installed fonts, so cross-platform pixel identity is not promised.

`RenderContext` optionally supplies `policy_id`, `outcome`, `termination_reason`, and `message`.
Pass no context when preparing policy input. The renderer accepts only a public Observation
and explicitly supplied presentation values; it never receives a Game, seed, snapshot, or
future schedule. Metadata is never added to an observation or auto-forwarded into rendering.

`RenderOptions` controls optional selection/inspection overlays, supplied hover coordinates,
legal actions, status badges, and outcome banners. Human controls compute these values via
the shared validator. No mouse or keyboard state is read by the renderer. The interactive
application uses the same board, HUD, and primitive drawing functions. Existing imports of
`pvz_game.ui.plant_art` and `zombie_art` remain available.

Export a verified final PNG or run the complete example:

```text
pvz replay recordings/limited.json --frame artifacts/limited.png
python examples/offscreen_replay.py
```

The example writes a metadata-bearing replay and a PPM frame from RGB bytes. Rendering and
annotations do not change the game's cutoff status: the engine can remain `running` while
the presentation says `TRUNCATED`.

### Source pins for external consumers

Source-pinned consumers must adopt the new package's Git commit and source manifest even
though its simulation compatibility identifier remains `1.0.0`. Run
`python tools/export_engine_pin.py` after committing the source to generate
`dist/engine-lock-1.2.1.json`. The file contains the commit, package/simulation versions,
rules hash, and SHA-256 hashes of every installed Python/TOML file, normalizing CRLF to LF.
Existing research installations and their pinned manifests are not automatically changed.
