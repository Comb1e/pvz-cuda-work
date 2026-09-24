"""Real-time contracts independent of the implementation's tick conversions."""

import pytest

from pvz_game import ENGINE_VERSION, PACKAGE_VERSION, Game, InitialPlant, LevelSpec, Rules, Spawn


def test_100hz_physical_units_and_incompatible_old_snapshot():
    rules = Rules()
    assert PACKAGE_VERSION == "1.4.0" and ENGINE_VERSION == "1.1.0"
    assert rules.game["tick_rate"] == 100
    assert rules.plants["peashooter"]["interval_ticks"] == 150
    assert rules.plants["potato_mine"]["first_ticks"] == 1400
    assert rules.plants["cherry_bomb"]["first_ticks"] == 120
    game = Game()
    game.reset(LevelSpec("clock", (Spawn(1, "basic", 0),), mowers=False))
    game.step()
    first = game.observe().zombies[0].x
    game.step(ticks=100)
    assert first - game.observe().zombies[0].x == rules.zombies["basic"]["speed"]
    assert game.observe().elapsed_seconds == 1.01
    snapshot = game.snapshot()
    snapshot["engine_version"] = "1.0.0"
    with pytest.raises(ValueError):
        game.restore(snapshot)


def test_income_preparation_and_timer_boundaries_in_seconds():
    game = Game()
    game.reset(
        LevelSpec(
            "income",
            (Spawn(10000, "basic", 0),),
            initial_sun=0,
            plants=(InitialPlant("sunflower", 2, 2),),
        )
    )
    game.step(ticks=599)
    assert game.observe().sun == 0
    game.step()
    assert game.observe().sun == 25  # six seconds to first sunflower production
    assert game.observe().plants[0].timer_ticks == 2400
