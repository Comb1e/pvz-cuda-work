# Current architecture

Lawn Lab has one game engine. Human controls, Python callers, and replay playback all
submit the same actions. The renderer only reads public observations.

```mermaid
flowchart LR
    Human[Mouse and keyboard] --> UI[Interactive controller]
    UI --> API[Game API]
    External[External Python project] --> API
    Replay[Replay playback] --> API
    Rules[TOML rules and scenarios] --> Engine[20 Hz engine]
    API --> Engine
    Engine --> View[Immutable observations and events]
    View --> Renderer[Shared board and HUD renderer]
    Renderer --> Window[Interactive surface]
    Renderer --> Pixels[Offscreen Surface or RGB24 bytes]
    View --> External
    Engine --> Snapshot[Complete JSON snapshot]
    UI --> Recorder[Action recorder]
    Recorder --> File[Replay JSON with hashes]
    File --> Replay
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
| `replay` | Record actions, verify state hashes, and carry detached external annotations |
| `art` | Original plant/zombie primitives and shared drawing helpers; palette/labels in `theme.toml` |
| `rendering` | Draw a public observation and explicit presentation options into a Surface or RGB bytes |
| `ui` | Map input to actions, pace simulation, call the shared renderer, and manage screens |
| `cli` | Launch games, verify/watch replays, export final frames, and measure headless execution |

The core uses Python's standard library. pygame is imported only by the UI and rendering
tools. The external research project owns observation encoding, rewards, action masks in
framework-specific form, time cutoffs, training, and evaluation protocols.

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
    Peas --> Deaths[Remove defeated zombies and count events]
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
    Running --> Won: All scheduled zombies defeated
    Running --> Lost: A living zombie reaches the house
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
| Potato Mine | Arming → Armed → Detonating → Removed |
| Cherry Bomb | Fusing → Exploding → Removed |
| Chomper | Ready → Digesting → Ready |
| Lawn mower | Ready → Moving → Spent |
| Interactive screen | Menu → Playing ↔ Paused → Ended; restart or return to menu |

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
identifier when rules and state semantics are unchanged: package 1.1.0 uses engine 1.0.0 and
schema version 1. There is no migration across incompatible snapshot versions.
Platform-independent integer rules are used, but cross-platform determinism has not yet
been experimentally verified; the tested environment is Python 3.12.3 on Windows 11.
