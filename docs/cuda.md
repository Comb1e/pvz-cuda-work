# Optional CUDA simulator

Install `pvz-research-game[cuda]` with Python 3.12 and an NVIDIA CUDA 12 compatible
driver. The extra pins CuPy 13.6.0, NVIDIA runtime 12.8.90 and NVRTC 12.8.93.
The Windows wheels supply headers and compiler DLLs; neither `nvcc` nor Visual
Studio is required. Ordinary CPU gameplay has no CUDA dependency.

```python
from pvz_game import Game
from pvz_game.cuda import CudaBatch

# Capacity must cover every resolved scenario, including all future spawns.
batch = CudaBatch(32, zombie_capacity=200)
batch.reset(["standard"] * 32, list(range(32)))
batch.step([0] * 32)  # Wait: one engine tick per game.
mask = batch.action_masks_device()  # CuPy bool[32, 406], remains on GPU.
```

Action 0 waits. Actions `1 + 45*p + 9*r + c` plant; `361 + 9*r + c`
dig. Accepted planting/digging is immediate with `per_tick=True`. A rejected
action or wait advances one tick. Explicit `per_tick=False, ticks=k` matches the
ordinary Python `Game.step` contract. Games can have different clocks/statuses.
Reset finished slots before stepping; trusted collectors can disable finished slots.

`reset(levels, seeds, indices=...)` and `restore(snapshots, indices=...)` validate
the entire submitted reset before mutating any slot. `step` checks host indices;
`step_device` is the trusted collector interface for contiguous int64 CuPy inputs.
The collector owns stream synchronization and valid action indices. Use
`cupy.cuda.ExternalStream(torch.cuda.current_stream().cuda_stream)` around both
interfaces when sharing arrays through DLPack. Retain array/stream owners.

The storage schema uses signed 64-bit integer positions, timers, remainders, and
IDs. Scenario values must fit that representation. Entity order is preserved in
compact arrays. One CUDA warp handles each game; one lane executes ordered combat
operations. Other kernels can parallelize masks and policy work. No competing
threads write damage to the same zombie. This design prioritizes equivalence;
occupancy/utilization is not itself a speed claim.

The zombie capacity is the complete resolved roster size. The projectile bound is
derived from maximum lifetime and at most two shots per tile per tick, including
replanting. A smaller requested capacity is rejected. For arbitrary mid-game
snapshots, allocate `projectile_bound(rules) + max_existing_projectiles` slots so
restored shots have their own headroom. No entity is clipped or discarded.
Modified combat rules are rejected with a CPU-backend instruction.

`diagnostic=True` enables ordered public events with `events(i)`. `snapshot(i)`,
`state_hash(i)` and `observe(i)` deliberately transfer data to the CPU; they are
for diagnostics/export, not the training hot path. `public_state_device()` is an
internal backend view, **not** a policy observation: the research encoder selects
public fields and excludes IDs, restrictions, schedules and RNG/seed metadata.
Compact facts use base-HP damage and distinguish plant and mower killing blows,
empty mower activations, activation sun, wall-nut damage and empty explosions.

Simulation version remains `1.2.0` only with differential checks against Python.
Research version 0.6.0 owns reward weights, task restrictions, timeout semantics,
PPO, and automatic-reset bookkeeping. Native JSON/compact replay playback remains
on the Python oracle; research GPU demonstrations must replay and match hashes
before publication.
