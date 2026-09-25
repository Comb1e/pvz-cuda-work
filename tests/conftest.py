import pytest

from pvz_game import Game, LevelSpec, Rules, Spawn


@pytest.fixture
def make_game():
    def make(*, spawns=None, plants=(), sun=9990, mowers=False, stationary=True, changes=None):
        raw = Rules().to_dict()
        if stationary:
            for z in raw["zombies"].values():
                z["speed"] = z["max_speed"] = 0
                if "pole_speed" in z:
                    z["pole_speed"] = z["pole_max_speed"] = 0
        if changes:
            changes(raw)
        game = Game(Rules(raw))
        # Keep an ordinary mechanics fixture running unless explicitly given no future spawns.
        if spawns is None:
            spawns = (Spawn(100000, "basic", 4),)
        game.reset(LevelSpec("fixture", tuple(spawns), sun, tuple(plants), mowers), seed=42)
        return game

    return make
