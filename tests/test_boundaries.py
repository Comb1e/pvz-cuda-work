import json
from pathlib import Path

import pytest

from pvz_game import Game, InitialPlant, Place, Spawn, Status, WaveSpec, load_scenario


def test_custom_generated_waves_are_deterministic():
    wave = WaveSpec("custom", (("basic",), ("conehead", "flag")), 10, 20, 3)
    a, b = Game(), Game()
    a.reset(wave, 18)
    b.reset(wave, 18)
    assert a.state_hash() == b.state_hash()
    assert a.observe().counts.initial_total == 3
    schedule = a.snapshot()["level"]["spawns"]
    assert 1000 <= schedule[0]["tick"] <= 1300
    assert all(3000 <= s["tick"] <= 3300 for s in schedule[1:])


@pytest.mark.parametrize(
    "wave",
    [
        WaveSpec("bad", ()),
        WaveSpec("bad", ((),)),
        WaveSpec("bad", (("unknown",),)),
        WaveSpec("bad", (("basic",),), jitter_seconds=25),
        WaveSpec("bad", (("basic",),), preparation_seconds=0.003),
    ],
)
def test_invalid_generated_waves_rejected(wave):
    with pytest.raises(ValueError):
        Game().reset(wave)


@pytest.mark.parametrize("filename,count", [("scenario.toml", 2), ("waves.toml", 6)])
def test_example_scenarios_load(filename, count):
    scenario = load_scenario(Path(__file__).parents[1] / "examples" / filename)
    assert Game().reset(scenario).counts.remaining == count


def test_moving_zombie_cannot_tunnel_through_a_projectile(make_game):
    def fast(raw):
        raw["zombies"]["basic"]["speed"] = raw["zombies"]["basic"]["max_speed"] = 200
        raw["game"]["projectile_speed"] = 50

    game = make_game(
        changes=fast,
        stationary=False,
        spawns=(Spawn(1, "basic", 0, x=2500),),
        plants=(InitialPlant("peashooter", 0, 0),),
    )
    next(iter(game._plants.values())).burst_due = 1
    # Pea goes .8 -> 1.3 tiles, zombie goes 2.5 -> .8 (blocked by plant).
    game.step()
    assert game.observe().zombies[0].health == 250
    assert not game.observe().projectiles


def test_moving_mower_catches_a_zombie_crossing_its_old_position(make_game):
    def fast(raw):
        raw["zombies"]["basic"]["speed"] = raw["zombies"]["basic"]["max_speed"] = 20
        raw["game"]["mower_speed"] = raw["game"]["mower_min_speed"] = 25

    game = make_game(
        stationary=False,
        changes=fast,
        mowers=True,
        spawns=(Spawn(1, "basic", 0, x=0), Spawn(2, "basic", 0, x=300)),
    )
    game.step()
    assert game.observe().mowers[0].x == 250
    # Next zombie crosses 300 -> 100, behind the mower's old x=250.
    result = game.step()
    assert result.status == Status.WON
    assert result.observation.counts.defeated == 2


def test_final_tick_attack_prevents_house_breach(make_game):
    def fast(raw):
        raw["zombies"]["basic"]["speed"] = raw["zombies"]["basic"]["max_speed"] = 1000
        raw["plants"]["peashooter"]["damage"] = 200
        raw["game"]["projectile_speed"] = 1000

    game = make_game(
        stationary=False,
        changes=fast,
        spawns=(Spawn(1, "basic", 0, x=9000),),
        plants=(InitialPlant("peashooter", 0, 0),),
    )
    next(iter(game._plants.values())).burst_due = 1
    assert game.step().status == Status.WON


def test_lost_game_cannot_be_relabelled_running(make_game):
    game = make_game(stationary=False, spawns=(Spawn(1, "basic", 0, x=0),))
    game.step(ticks=300)
    assert game.observe().status == Status.LOST
    snapshot = game.snapshot()
    snapshot["status"] = "running"
    with pytest.raises(ValueError, match="outcome"):
        game.restore(snapshot)


@pytest.mark.parametrize("field,value", [("due", -1), ("row", 0.5), ("state", "digesting")])
def test_corrupt_entity_snapshot_is_rejected(make_game, field, value):
    game = make_game()
    game.step(Place("peashooter", 0, 0))
    before = game.state_hash()
    snap = json.loads(json.dumps(game.snapshot()))
    snap["plants"][0][field] = value
    with pytest.raises(ValueError):
        game.restore(snap)
    assert game.state_hash() == before


def test_duplicate_entities_in_snapshot_rejected(make_game):
    game = make_game()
    game.step(Place("sunflower", 0, 0))
    snapshot = game.snapshot()
    snapshot["plants"].append(dict(snapshot["plants"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        game.restore(snapshot)
