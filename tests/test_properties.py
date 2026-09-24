import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pvz_game import Dig, Game, InitialPlant, LevelSpec, Place, Rules, Spawn, Status, Wait
from pvz_game.config import PLANT_TYPES


@settings(max_examples=25, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(0, 9), st.integers(-1, 5), st.integers(-1, 9), st.integers(1, 120)),
        min_size=1,
        max_size=35,
    )
)
def test_generated_actions_preserve_invariants(sequence):
    game = Game()
    game.reset("hard", 12)
    for kind, row, col, ticks in sequence:
        if game.observe().status != Status.RUNNING:
            break
        action = (
            Place(PLANT_TYPES[kind], row, col)
            if kind < 8
            else (Dig(row, col) if kind == 8 else Wait())
        )
        predicted = game.validate_action(action)
        result = game.step(action, ticks=ticks)
        assert result.action_result == predicted
        obs = result.observation
        assert 0 <= obs.sun <= game.rules.game["sun_cap"]
        assert len({(p.row, p.col) for p in obs.plants}) == len(obs.plants)
        ids = (
            [p.id for p in obs.plants]
            + [z.id for z in obs.zombies]
            + [p.id for p in obs.projectiles]
        )
        assert len(ids) == len(set(ids))
        assert all(p.health > 0 for p in obs.plants)
        assert all(z.health > 0 and z.armor >= 0 for z in obs.zombies)
        counts = obs.counts
        assert counts.remaining == counts.alive + counts.not_yet_spawned
        assert counts.initial_total == counts.defeated + counts.remaining
        assert counts.spawned == counts.defeated + counts.alive
    before = game.state_hash()
    game.restore(json.loads(json.dumps(game.snapshot())))
    assert game.state_hash() == before


def test_legal_actions_predict_execution_from_identical_snapshot(make_game):
    game = make_game(sun=200, plants=(InitialPlant("wall_nut", 1, 1),))
    snapshot = game.snapshot()
    actions = game.legal_actions()
    for action in actions:
        game.restore(snapshot)
        assert game.step(action).action_result.accepted


@pytest.mark.parametrize(
    "name,count,waves", [("easy", 15, 5), ("standard", 40, 10), ("hard", 75, 15)]
)
def test_presets_have_fixed_total_and_seeded_variation(name, count, waves):
    game = Game()
    obs = game.reset(name, 42)
    assert obs.counts.initial_total == count
    assert obs.total_waves == waves
    before = game.snapshot()["level"]["spawns"]
    game.reset(name, 43)
    assert game.snapshot()["level"]["spawns"] != before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["plants"]["sunflower"].update(cost=-1),
        lambda r: r["plants"]["cherry_bomb"].update(first_seconds=1.234),
        lambda r: r["game"].update(rows=6),
        lambda r: r["game"].update(sky_sun_seconds=0),
        lambda r: r["game"].update(unknown=1),
        lambda r: r["zombies"].update(invented={}),
        lambda r: r["zombies"]["basic"].update(speed=float("nan")),
    ],
)
def test_invalid_rule_values_rejected(mutate):
    data = Rules().to_dict()
    mutate(data)
    with pytest.raises(ValueError):
        Rules(data)


@pytest.mark.parametrize(
    "level",
    [
        LevelSpec("invalid", (Spawn(-1, "basic", 0),)),
        LevelSpec("invalid", (Spawn(1, "basic", 5),)),
        LevelSpec("invalid", (Spawn(1, "unknown", 0),)),
        LevelSpec("invalid", (Spawn(1, "basic", 0, x=10000),)),
        LevelSpec("invalid", initial_sun=-1),
        LevelSpec(
            "invalid", plants=(InitialPlant("wall_nut", 0, 0), InitialPlant("sunflower", 0, 0))
        ),
    ],
)
def test_invalid_scenario_values_rejected(level):
    with pytest.raises(ValueError):
        Game().reset(level)
