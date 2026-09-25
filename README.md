# Lawn Lab

A playable daytime PvZ-style game with a deterministic Python engine. Build a garden,
defend five lanes, or control the same simulation from a separate research project.
The core has **no third-party runtime dependencies**; the optional interface uses pygame-ce.

Eight plants, five zombies, three scenarios, automatic sun collection, exact remaining
zombie counts, snapshots, and verified action replays are included. Training algorithms,
rewards, tensor observations, and learning-framework wrappers belong to your external project.

Version 1.5.0 runs at 100 Hz (simulation compatibility 1.2.0) and includes an optional CUDA batch simulator ([API and setup](docs/cuda.md)).
The renderer shows zombie progress as defeated/total, such as `2/15`, across gameplay and
demos. Compact recordings support live viewing and a seekable timeline with 0.5×–8× speeds.

Mechanics, public headless state, RNG, and reconstruction limits are documented in
[PC mechanics](docs/math/pc-mechanics.md). Head loss neutralizes a threat; its visible
body can continue decaying without producing plant damage credit.

## Research demos

The native replay command now also opens research `.pvzdemo` files containing
`pvz-rl/actions-v1`, including multiple plant/dig operations within one tick:

```powershell
pvz replay "PATH_TO_DEMO.pvzdemo" --watch --speed 2
```

A source launcher can reuse another environment without reinstalling its game:

```powershell
.\tools\watch_demo.ps1 -Replay "PATH_TO_DEMO.pvzdemo" -Python "E:/Projects/Tower-Defence-AI/PVZ-plant/.venv/Scripts/python.exe" -Speed 2
# Add -VerifyOnly to check hashes without opening a window.
```

This release reads 100 Hz recordings only. Previous 20 Hz snapshots and replays
have incompatible simulation versions and require their original engine; no conversion
or legacy simulator is included. Research training installs a verified Git archive of
this repository into its existing environment.

## Play

Python 3.12 or newer is required. From this folder on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui,dev]"
.\.venv\Scripts\pvz.exe play
```

Start a particular game:

```powershell
.\.venv\Scripts\pvz.exe play --level standard --seed 42
```

On other platforms, use the corresponding environment's `python` and `pvz` executables.
Windows is the verified platform for this release.

| Control | Action |
|---|---|
| 1–8 / click a card | Select a plant |
| Click a lawn tile | Plant, or dig with the shovel |
| S / shovel button | Select the shovel |
| Right-click / Escape | Cancel selection; Escape pauses when nothing is selected |
| Space | Pause/resume |
| Period while paused | Advance one tick |
| Speed button | 1×, 2×, or 4× simulation speed |
| I | Toggle inspection; hover a plant or zombie for details |
| R | Restart the same scenario and seed |
| F5 | Save a replay under `recordings/` |

At the level menu, type digits or Backspace to edit the seed. Sun credits automatically.
The main zombie counter shows defeated/total, such as `2/15`. Total includes every zombie
scheduled for the level, and stays fixed as zombies spawn or are defeated. Remaining,
on-lawn, and upcoming counts are also shown; future identities, lanes, and exact spawn times
are not shown. All eight species are supported; slow cards have their original initial recharge delays.

## Control from another project

Install the core into that project's environment, without the UI extra:

```powershell
python -m pip install -e E:\Projects\pvz-cuda-work
```

```python
from pvz_game import Game, Place, Status, Wait

game = Game()
observation = game.reset(level="standard", seed=42)
result = game.step(Place("sunflower", row=2, col=0), ticks=4)
assert result.action_result.accepted

observation = game.observe()
legal_actions = game.legal_actions()
snapshot = game.snapshot()
result = game.step(Wait(), ticks=20)
game.restore(snapshot)

while game.observe().status == Status.RUNNING:
    result = game.step(Wait(), ticks=20)
print(result.status)
```

One tick is 0.01 simulated seconds. An action is applied once, before the requested ticks.
Every result includes detached state, events, action acceptance, status, and ticks advanced.
There is no reward and no automatic time limit. See [the API contract](docs/api.md) and
[the standalone integration example](examples/external_control.py).

## Rules and scenarios

| Preset | Waves | Zombies |
|---|---:|---:|
| Easy | 5 | 15 |
| Standard | 10 | 40 |
| Hard | 15 | 75 |

Wave sizes ramp up so the opening economy has time to develop. Hard shares standard's
opening ten wave compositions, then adds five waves of seven zombies each. Generation
chooses lanes and bounded timing jitter from the supplied seed, once at reset.

Balance lives in [rules.toml](src/pvz_game/data/rules.toml), preset compositions in
[levels.toml](src/pvz_game/data/levels.toml), and presentation settings in
[ui.toml](src/pvz_game/data/ui.toml). Copy a configuration before changing it for research.

```powershell
pvz play --scenario examples/scenario.toml --seed 42
pvz play --scenario examples/waves.toml --seed 42
pvz play --level easy --rules my-rules.toml --ui-config my-ui.toml
```

`LevelSpec` supports explicit spawn schedules and initial plants. `WaveSpec` supports
custom seeded wave generation. [The rules document](docs/rules.md) defines collision,
timing, armor, special behavior, and the intentional differences from the original game.

## Replays and checks

```powershell
pvz demo --script examples/demo.toml --output demos/sample.pvzdemo
pvz demo --script examples/demo.toml --output demos/live.pvzdemo --live --speed 4
pvz replay demos/sample.pvzdemo --watch --speed 2
pvz play --level standard --seed 42 --record recordings/my-game.json
pvz replay recordings/my-game.json
pvz replay recordings/my-game.json --watch
pvz replay recordings/my-game.json --frame artifacts/final.png
pvz replay tests/fixtures/hard-seed42.json --watch
pvz benchmark --level standard --ticks 20000
python tools/benchmark_suite.py
python -m pytest -q
ruff check src tests tools examples
python -m build
```

Replay verification checks tick indices, periodic state hashes, and the final state.
Snapshots and replays require the same engine/schema versions; snapshots also require
identical rules. Replay files embed their resolved rules and spawn schedule.

The [demo API guide](docs/demos.md) covers parameterized generation and recording operations
from an existing program through `DemoSession`. Demos store compressed operations and render
while watching. The timeline supports dragging, Left/Right five-second seeks, Home/End,
pause, and single-tick stepping. Add `--overwrite` only to intentionally replace a demo.

Recorders accept optional JSON metadata such as `policy_id`, `checkpoint_sha256`,
`outcome="truncated"`, and `termination_reason="time_limit"`. These annotations stay outside
observations and simulation hashes. The underlying game status remains `running` when an
external controller stops it. See [the metadata and rendering API](docs/api.md) and
[the offscreen example](examples/offscreen_replay.py) for Surface and RGB24 output.

`PACKAGE_VERSION` is `1.3.0`; the simulation compatibility identifier `ENGINE_VERSION`
remains `1.0.0`. Source-pinned consumers still need the new commit and file manifest.
After committing source changes, `python tools/export_engine_pin.py` writes
`the consumer project's engine-lock.json` for adoption alongside the new package installation.

All three presets include a winning seed-42 replay in `tests/fixtures/`. The small scripted
controller in `tools/record_playthroughs.py` exists to generate these acceptance fixtures;
it is not a trained model or evidence of generalization to other seeds.

## Project notes

- [Architecture and data flow](docs/architecture.md)
- [Validation results and measured performance](docs/validation.md)
- [Version history and known limitations](docs/iteration.md)
- [Research and project references](docs/references.md)

The game code and primitive-based drawings were written for this project. Gameplay is
inspired by Plants vs. Zombies; no original game assets or referenced-project code are bundled.
