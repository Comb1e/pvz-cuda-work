# Current architecture

Lawn Lab has a Python reference simulator and an optional CUDA batch simulator.
Human controls and replay playback use the Python API. CUDA training batches use
the same rules and operation order. The renderer only reads public observations.

```mermaid
flowchart LR
    Human[Mouse and keyboard] --> UI[Interactive controller]
    UI --> API[Game API]
    External[External Python project] --> API
    External --> Demo[Demo session]
    Script[TOML or scheduled operations] --> Generate[Demo generator]
    Generate --> Demo
    Demo --> Recorder
    Demo --> API
    Demo --> Live[Live preview]
    Live --> Renderer
    Replay[Replay playback] --> API
    Rules[TOML rules and scenarios] --> Engine[100 Hz engine]
    Rules --> Resolve[CPU scenario resolution]
    Resolve --> GPU[CUDA arrays and ordered game kernels]
    External --> GPU
    GPU --> Numeric[Device state and compact event facts]
    Numeric --> External
    GPU --> Compare[Diagnostic snapshots and ordered events]
    Compare --> Snapshot
    API --> Engine
    Engine --> View[Immutable observations and events]
    View --> Renderer[Shared board and HUD renderer]
    Renderer --> Window[Interactive surface]
    Renderer --> Pixels[Offscreen Surface or RGB24 bytes]
    View --> External
    Engine --> Snapshot[Complete JSON snapshot]
    UI --> Recorder[Action recorder]
    Recorder --> File[JSON or compressed demo with hashes]
    File --> Format[Replay format dispatch]
    Format --> Replay
    Format --> Instant[Research action-phase player]
    Instant --> API
    File --> Metadata[Optional replay annotations]
    Metadata --> Context[Explicit presentation context]
    Context --> Renderer
```

## Ownership

| Component | Responsibility |
|---|---|
| `config` | Parse and validate rules, explicit schedules, and generated waves |
| `types` | Frozen actions, events, observations, outcomes, and API versions |
| `engine` | Own all mutable entities, timers, resources, RNG, and game outcomes |
| `cuda` | Optional batched integer simulation, checked reset/step, public numeric state, event facts, diagnostic snapshots and hashes |
| `replay` | Record actions, verify state hashes, and carry detached external annotations |
| `demo` | Validate scheduled actions, record submitted calls, finalize external outcomes and atomic files |
| `demo_ui` | Pace live session ticks, process preview input, and render public observations |
| `art` | Original plant/zombie primitives and shared drawing helpers; palette/labels in `theme.toml` |
| `rendering` | Draw a public observation and explicit presentation options into a Surface or RGB bytes |
| `ui` | Map input to actions, pace simulation, call the shared renderer, and manage screens |
| `cli` | Launch games, verify/watch replays, export final frames, and measure headless execution |

`DemoSession` wraps a reset Game and one Recorder. Recorder's internal presentation hooks
allow the live preview to run between fixed ticks while retaining one entry per submitted
call. Headless calls retain the fast batched engine path. Both paths return equivalent events,
action results, observations, and hashes. The session verifies its complete recording before
publishing it atomically. A cancelled call records only its completed ticks.

```mermaid
stateDiagram-v2
    [*] --> Recording
    Recording --> Finalizing: finish, context exit, error, or window close
    Finalizing --> Closed: Verify and publish completed operations
    Closed --> Closed: Repeated finish returns same result
```

The generator fills gaps between scheduled operations with waits. It stops on a natural
outcome or an explicit cutoff; it uses the same session for recording and optional live
preview. Live pause stops requested ticks without changing the Game status. The caller owns
execution between streaming calls; live preview does not start a worker thread.

The core uses Python's standard library. pygame is imported only by the UI and rendering
tools. The external research project owns observation encoding, rewards, action masks in
framework-specific form, time cutoffs, training, and evaluation protocols.

The shared HUD displays `counts.defeated/counts.initial_total`, such as `2/15`. All views use
this one formatter; integer observation counts and game outcomes count neutralized threats; headless bodies remain in the entity list until removal.

`BoardRenderer` accepts an observation, optional `RenderContext`, and optional `RenderOptions`.
It never takes a Game, seed, snapshot, or future schedule. Selection, hover coordinates, legal
actions, and inspection/effects come from explicit options. The interactive controller gets
legal actions from the engine's shared validator; drawing never reads input devices.

The renderer initializes fonts only. `render` owns a fresh output surface; `draw` uses a
caller-owned native-size surface and restores its clip. RGB24 bytes are immutable, row-major,
top row first, with no padding. Optional scaling preserves aspect ratio with letterboxing.
The UI owns its display and event loop; offscreen consumers need neither.

## Data and reset flow

```mermaid
flowchart TD
    Reset[reset with scenario and seed] --> Validate[Validate before replacing a live game]
    Validate --> RNG[Create an instance-owned random generator]
    RNG --> Resolve[Resolve all wave lanes and times]
    Resolve --> State[Create empty entities and ready cards]
    State --> Initial[Add configured initial plants and mowers]
    Initial --> Observe[Export immutable current state]
```

Generated schedules are fixed at reset. Observations expose only current entities and
aggregate future counts. Complete snapshots also expose the schedule and RNG state.
This difference is deliberate: snapshots are debugging data, not normal agent observations.

Each entity receives a monotonically increasing ID. Dictionary insertion order and
explicit position/ID ordering resolve ties. No shared global RNG or renderer timer affects
the engine. Timers use integer ticks; positions use fixed-point units. Movement retains
fractional remainders when speeds do not divide evenly into ticks.

## One step

```mermaid
flowchart TD
    Request[Action and positive tick count] --> Check[Shared action validator]
    Check --> Apply[Apply once or record rejection]
    Apply --> Clock[Advance clock and cooldowns]
    Clock --> Spawn[Spawn due zombies and credit sky sun]
    Spawn --> Plants[Plant state changes and attacks]
    Plants --> Peas[Move projectiles with swept collision]
    Peas --> Deaths[Remove dead bodies]
    Deaths --> Zombies[Zombie movement, vaulting, and bites]
    Zombies --> Mowers[Mower activation and swept movement]
    Mowers --> Cleanup[Remove destroyed entities]
    Cleanup --> End{Won or lost?}
    End -->|yes| Export[Return state and events]
    End -->|no, ticks left| Clock
    End -->|no, request finished| Export
```

Projectile sweeps include zombie movement after projectiles advance. Mower sweeps compare
zombies' old and new positions, so opposite-moving objects cannot pass through one another.
Damage, targeting, removal, resource credit, and legality each have one implementation.
Events count defeats explicitly, including ticks with both new spawns and deaths.

## State transitions

```mermaid
stateDiagram-v2
    [*] --> Running
    Running --> Won: All scheduled threats neutralized
    Running --> Lost: A headed zombie reaches the house
    Won --> Running: reset
    Lost --> Running: reset
```

```mermaid
stateDiagram-v2
    [*] --> CarryingPole
    CarryingPole --> Vaulting: First blocking plant
    Vaulting --> Walking: Landing timer ends
    Walking --> Biting: Contact with plant
    Biting --> Walking: Plant removed
    CarryingPole --> Dead: Lethal damage
    Vaulting --> Dead: Lethal damage
    Walking --> Dead: Lethal damage
    Biting --> Dead: Lethal damage
```

| Entity | Other transitions |
|---|---|
| Ordinary zombie | Walking ↔ Biting → Dead |
| Potato Mine | Arming → Rising → Armed → Detonating → Removed |
| Cherry Bomb | Fusing → Exploding → Removed |
| Chomper | Ready → Biting → Digesting → Recovering → Ready |
| Lawn mower | Ready → Moving → Spent |
| Interactive screen | Menu → Playing ↔ Paused → Ended; restart or return to menu |

```mermaid
stateDiagram-v2
    Playing --> Paused: Pause
    Paused --> Playing: Resume
    Playing --> Seeking: Timeline or seek key
    Paused --> Seeking: Timeline or seek key
    Ended --> Seeking: Timeline or seek key
    Seeking --> Playing: Target reached, previously playing
    Seeking --> Paused: Target reached, previously paused or ended
    Playing --> Ended: Verified recording end
    Seeking --> Ended: Target is recording end
```

Seeking restores the nearest usable in-memory snapshot and replay cursor, then advances
through the same Playback step implementation. The UI consumes bounded chunks between input
frames. The initial snapshot plus at most 64 recent snapshots are retained, spaced every 200
ticks. Cache entries include the latest operation for correct feedback after rewinding.
Snapshots restore the existing Game instance; references held by a controller remain valid.
Seek caches and transient rendering effects are never serialized into demo files.

Detonation and removal can occur in the same tick; events make that transition observable.
Pause belongs to the UI. It stops asking the engine to advance. A frame accumulator keeps
unprocessed time rather than skipping simulation ticks when rendering is slow.

## Reproducibility boundary

Observations are frozen dataclasses containing only frozen values. Snapshots are detached
JSON-safe dictionaries. Restore validates a separate candidate game before replacing the
live instance. A replay embeds its original snapshot, records actions at exact ticks, and
checks hashes at checkpoints and completion. Tick batching does not change final state.

Replay metadata contains finite JSON annotations, copied on input and export. It never
enters snapshots, observations, actions, or state hashes. State verification checks simulation
consistency, not the authenticity of a caller-supplied policy name or checkpoint checksum.

```mermaid
flowchart TD
    State[Actual engine status] --> Terminal{Won or lost?}
    Terminal -->|yes| EngineOutcome[Show actual engine outcome]
    Terminal -->|no| Done{Playback fully verified?}
    Done -->|no| Running[Show running]
    Done -->|yes| Cutoff{External truncated or interrupted label?}
    Cutoff -->|yes| ExternalOutcome[Show external cutoff]
    Cutoff -->|no| Running
```

`Playback.display_outcome` implements this resolution. Direct renderer users supply their
presentation context explicitly and decide when an external cutoff applies. Neither path
changes the engine's Running/Won/Lost state machine.

Schema and engine versions are explicit. Package releases can share a simulation compatibility
identifier when rules and state semantics are unchanged: package 1.5.0 uses engine 1.2.0 and
snapshot/CUDA schema version 2. There is no migration across incompatible snapshot versions.
Platform-independent integer rules are used, but cross-platform determinism has not yet
been experimentally verified; the tested environment is Python 3.12.3 on Windows 11.

## Research recording playback

`Playback` accepts ordinary version 1 and `pvz-rl/actions-v1`. The latter dispatches
into `action_replay`, which applies zero-time plant/dig operations between normal
combat ticks. It has no learning-library dependency. Seeking includes all instant
operations at the requested tick, verifies hashes, and preserves game identity.
The normal Game API continues requiring positive ticks. Unknown formats fail.


## Production and combat phases

The [mechanics contract](math/pc-mechanics.md) defines timing, ranges and
reconstruction limits. Every game owns a portable gameplay RNG separate from
scenario generation. Its state and sky production counters are checkpointed;
CUDA headers carry them alongside entity phases. Public views expose headless
state and current health, but never the RNG or future schedule.

```mermaid
stateDiagram-v2
    Headed --> Headless: Body HP below one third
    Headed --> Removed: Lethal hit or swallow
    Headless --> Removed: Autonomous decay or later hit
```

Only the first transition out of Headed increments the neutralized count.
Autonomous decay emits its own event and cannot masquerade as plant damage.
Headless bodies cannot bite, vault, activate an idle mower or breach the house.
Victory counts neutralized threats, including those with a body still visible.

Mine phases are underground, rising, armed, detonated. Chomper phases are ready,
biting, caught/missed, digesting, recovering, ready. Shooter cycle deadlines run
even without targets; target acquisition schedules a separate shot windup.
