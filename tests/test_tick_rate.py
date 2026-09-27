"""Real-time contracts independent of the implementation's tick conversions."""

import pytest

from pvz_game import ENGINE_VERSION, PACKAGE_VERSION, Game, InitialPlant, LevelSpec, Rules, Spawn


def test_100hz_physical_units_and_incompatible_old_snapshot():
    rules = Rules()
    assert PACKAGE_VERSION == "1.7.0" and ENGINE_VERSION == "1.4.0"
    assert rules.game["tick_rate"] == 100
    assert rules.plants["peashooter"]["interval_ticks"] == 150
    assert rules.plants["potato_mine"]["first_ticks"] == 1500
    assert rules.plants["cherry_bomb"]["first_ticks"] == 100
    game = Game()
    game.reset(LevelSpec("clock", (Spawn(1, "basic", 0),), mowers=False))
    game.step()
    first = game.observe().zombies[0].x
    game.step(ticks=100)
    assert (
        100 < first - game.observe().zombies[0].x < 300
    )  # Instantaneous gait, not constant velocity.
    assert game.observe().elapsed_seconds == 1.01
    snapshot = game.snapshot()
    snapshot["engine_version"] = "1.0.0"
    with pytest.raises(ValueError):
        game.restore(snapshot)


def test_initial_slow_recharge_and_income_bounds():
    game = Game()
    obs = game.reset(
        LevelSpec(
            "income",
            (Spawn(10000, "basic", 0),),
            initial_sun=0,
            plants=(InitialPlant("sunflower", 2, 2),),
        )
    )
    assert [c.cooldown_ticks for c in obs.cards] == [0, 0, 2001, 3501, 2001, 0, 0, 0]
    first = obs.plants[0].timer_ticks
    assert 300 <= first <= 1250
    result = game.step(ticks=first)
    produced = [
        e for e in result.events if e.kind == "SunProduced" and e.get("source") == "sunflower"
    ]
    assert len(produced) == 1 and produced[0].tick == first
    assert 2350 <= game.observe().plants[0].timer_ticks <= 2500
    assert game.observe().elapsed_seconds == first / 100
