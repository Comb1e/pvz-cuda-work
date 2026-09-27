# Lawn Lab

A deterministic daytime lawn-defense game with eight plants, five zombie types,
three custom wave stages, automatic sun collection, verified replays and an
optional CUDA simulator. The game dependency is separate from learning code.

Package **1.7.0**, simulation compatibility **1.4.0**, runs at 100 Hz. Collision
uses attack rectangles, age-cadenced bites, positive projectile overlap and swept
mower contact. Earlier recordings require their original engine.

## Requirements and installation

Python 3.12 or newer and Git. The core has no third-party runtime dependencies;
pygame-ce supplies the optional UI. From this checkout on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui,dev]"
```

Use the corresponding environment's Python on other platforms. See
[CUDA setup](docs/cuda.md) for the optional NVIDIA runtime.

## First useful command

```powershell
.\.venv\Scripts\pvz.exe play --level easy --seed 42
```

Choose a card with 1–8, click an empty tile, or use S for the shovel.
Space pauses; period advances one tick while paused. The native game's R key
restarts. External human-recording sessions can disable restarting.

## Common checks

```powershell
pvz replay tests/fixtures/v17/hard-seed42.json
pvz replay PATH_TO_DEMO.pvzdemo --watch --speed 2
python -m pytest -q
python -m ruff check src tests tools examples
python -m ruff format --check src tests tools examples
python -m pip check
python -m build
```

The current winning seed-42 fixtures live in `tests/fixtures/v17/`; earlier
fixtures are preserved for their original engines. The unchanged scripted
verification controller is not a trained policy or a generalization claim.

- [Public API, snapshots and metadata](docs/api.md)
- [Rules and controls](docs/rules.md)
- [Demo recording and playback](docs/demos.md)
- [Architecture and data flow](docs/architecture.md)
- [Collision mathematics and reconstruction limits](docs/math/gait-and-geometry.md)
- [Validation](docs/validation.md)
- [Iteration history](docs/iteration.md)
- [Inspected references](docs/references.md)

No original game artwork or referenced-project code is bundled.
