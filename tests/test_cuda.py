"""Differential controls: CPU is the oracle, never expected data from the GPU."""

import random

import pytest

from pvz_game import Game, LevelSpec, Place, Spawn, Status, Wait
from pvz_game.config import PLANT_TYPES, ZOMBIE_TYPES, InitialPlant


@pytest.fixture(scope="module")
def cuda():
    pytest.importorskip("cupy")
    from pvz_game.cuda.backend import cupy_runtime

    try:
        cp = cupy_runtime()
        cp.cuda.runtime.getDeviceCount()
    except Exception as exc:
        pytest.skip(f"CUDA device unavailable: {exc}")
    from pvz_game.cuda import CudaBatch

    return CudaBatch


def encode(action):
    from pvz_game import Dig

    if isinstance(action, Wait):
        return 0
    if isinstance(action, Dig):
        return 361 + action.row * 9 + action.col
    return 1 + 45 * PLANT_TYPES.index(action.plant_type) + 9 * action.row + action.col


def compare(batch, cpu, actions, *, per_tick=False):
    expected = []
    for game, action in zip(cpu, actions):
        if per_tick and not isinstance(action, Wait) and game.validate_action(action).accepted:
            # Public action-only adapter independent of CUDA implementation.
            advance = game._advance
            game._advance = lambda: None
            try:
                result = game.step(action)
            finally:
                game._advance = advance
        else:
            result = game.step(action)
        expected.append(result)
    batch.step([encode(a) for a in actions], per_tick=per_tick)
    for i, (game, result) in enumerate(zip(cpu, expected)):
        assert batch.snapshot(i) == game.snapshot(), (i, game.observe().tick)
        assert batch.state_hash(i) == game.state_hash()
        assert batch.observe(i) == game.observe()
        assert batch.events(i) == result.events
        header = batch.header[i].get()
        assert bool(header[12]) == result.action_result.accepted
        assert int(header[14]) == result.ticks_advanced
        gpu_legal = set(batch.action_masks_device()[i].get().nonzero()[0].tolist())
        assert gpu_legal == {encode(a) for a in game.legal_actions()}


@pytest.mark.parametrize("plant", PLANT_TYPES)
def test_each_plant_all_zombies_order_and_integer_parity(cuda, plant):
    level = LevelSpec(
        "combat",
        tuple(Spawn(1 + 30 * j, kind, j % 5, x=3500) for j, kind in enumerate(ZOMBIE_TYPES)),
        initial_sun=9990,
        plants=tuple(InitialPlant(plant, row, 2) for row in range(5)),
    )
    batch = cuda(1, zombie_capacity=5, diagnostic=True, max_step_ticks=1)
    batch.reset([level], [42])
    game = Game()
    game.reset(level, 42)
    for tick in range(1800):
        compare(batch, [game], [Wait()])
        if game.observe().status != Status.RUNNING:
            break


def test_mixed_instant_actions_dig_rejections_and_resets(cuda):
    from pvz_game import Dig

    level = LevelSpec("operations", (Spawn(20, "basic", 0, x=1400),), initial_sun=200)
    batch = cuda(2, zombie_capacity=1, diagnostic=True, max_step_ticks=1)
    batch.reset([level, level], [0, 1])
    games = [Game(), Game()]
    for i, game in enumerate(games):
        game.reset(level, i)
    for actions in (
        [Place("sunflower", 0, 0), Wait()],
        [Place("peashooter", 0, 1), Place("wall_nut", 0, 0)],
        [Place("sunflower", 0, 0), Dig(0, 0)],
        [Dig(0, 0), Dig(0, 1)],
    ):
        compare(batch, games, actions, per_tick=True)
    batch.reset([level], [9], indices=[1])
    assert batch.state_hash(0) == games[0].state_hash()
    fresh = Game()
    fresh.reset(level, 9)
    assert batch.state_hash(1) == fresh.state_hash()


def test_seeded_legal_and_invalid_traces(cuda):
    batch = cuda(1, zombie_capacity=200, diagnostic=True, max_step_ticks=1)
    game, rng = Game(), random.Random(7)
    game.reset("hard", 8)
    batch.reset(["hard"], [8])
    for step in range(2600):
        action = rng.choice(game.legal_actions()) if step % 9 == 0 else Wait()
        compare(batch, [game], [action], per_tick=True)
        if game.observe().status != Status.RUNNING:
            break


def test_capacity_rejects_atomically_and_rules_stay_cpu(cuda):
    from pvz_game import Rules
    from pvz_game.cuda import CapacityError

    batch = cuda(2, zombie_capacity=1)
    batch.reset([LevelSpec("empty"), LevelSpec("empty")], [0, 1])
    hashes = [batch.state_hash(i) for i in range(2)]
    crowded = LevelSpec("overflow", (Spawn(1, "basic", 0), Spawn(1, "basic", 0)))
    with pytest.raises(CapacityError):
        batch.reset([LevelSpec("different"), crowded], [3, 4])
    assert hashes == [batch.state_hash(i) for i in range(2)]
    with pytest.raises(CapacityError):
        cuda(1, zombie_capacity=1, projectile_capacity=1)
    changed = Rules().to_dict()
    changed["plants"]["peashooter"]["damage"] += 1
    with pytest.raises(ValueError, match="CPU"):
        cuda(1, zombie_capacity=1, rules=Rules(changed))
    with pytest.raises(ValueError):
        batch.step([0, 406])
    assert hashes == [batch.state_hash(i) for i in range(2)]
    batch.step([0, 0])
    assert [batch.observe(i).status for i in range(2)] == [Status.WON] * 2


@pytest.mark.parametrize("level", ["easy", "standard", "hard"])
def test_archived_success_and_failure_replay_hashes(cuda, level):
    import json
    from pathlib import Path

    from pvz_game.replay import decode_action

    payload = json.loads((Path(__file__).parent / "fixtures" / f"{level}-seed42.json").read_text())
    batch = cuda(1, zombie_capacity=len(payload["initial"]["level"]["spawns"]), diagnostic=True)
    batch.restore([payload["initial"]])
    game = Game()
    game.restore(payload["initial"])
    for entry in payload["entries"]:
        action = decode_action(entry["action"])
        result = game.step(action, ticks=entry["ticks"])
        batch.step([encode(action)], ticks=entry["ticks"], per_tick=False)
        assert batch.events(0) == result.events
        if "state_hash" in entry:
            assert batch.state_hash(0) == entry["state_hash"] == game.state_hash()
    assert batch.state_hash(0) == payload["final_hash"]
    assert batch.observe(0).status.value == payload["final_status"]


def test_restore_crowds_mower_sweep_and_signed_boundaries(cuda):
    from pvz_game.cuda.backend import projectile_bound

    level = LevelSpec(
        "crowded",
        tuple(Spawn(1, k, i % 5, x=10) for i, k in enumerate(ZOMBIE_TYPES * 30)),
        initial_sun=200,
    )
    game = Game()
    game.reset(level, 3)
    batch = cuda(1, zombie_capacity=150, diagnostic=True, max_step_ticks=1)
    batch.reset([level], [3])
    compare(batch, [game], [Wait()])
    # 120 ordinary zombies move to/cross the trigger; remaining pole zombies
    # also cross. Simultaneous mower damage uses each row's original order.
    assert game.observe().counts.defeated > 100
    later = Game()
    later.reset(
        LevelSpec(
            "shots", (Spawn(1, "buckethead", 0, x=9200),), plants=(InitialPlant("snow_pea", 0, 0),)
        ),
        2,
    )
    later.step(ticks=5)
    restored = cuda(
        1,
        zombie_capacity=1,
        projectile_capacity=projectile_bound(later.rules) + len(later.snapshot()["projectiles"]),
        diagnostic=True,
        max_step_ticks=1,
    )
    restored.restore([later.snapshot()])
    assert restored.state_hash(0) == later.state_hash()
    for _ in range(25):
        compare(restored, [later], [Wait()])
