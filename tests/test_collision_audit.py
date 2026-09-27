from pvz_game import InitialPlant, Spawn
from pvz_game.mechanics import attack_contact, projectile_contact


def test_attack_contact_requires_twenty_source_pixels_and_is_lane_local():
    assert attack_contact(0, 450, 1000)
    assert not attack_contact(0, 451, 1000)
    assert not attack_contact(1, 450, 1000)


def test_projectile_edge_tangency_is_a_miss():
    # With 80 units per source pixel, the pea's left edge at 57px only touches
    # the zombie body ending at 42px plus its 15px projectile lead.
    assert not projectile_contact(0, 57, 57, 80)
    assert projectile_contact(0, 56, 56, 80)


def test_lethal_custom_one_and_two_hp_bodies_count_once(make_game):
    def custom(raw):
        raw["zombies"]["basic"]["health"] = 1
        raw["zombies"]["basic"]["max_speed"] = raw["zombies"]["basic"]["speed"] = 0

    game = make_game(changes=custom, spawns=(Spawn(1, "basic", 0, x=2000),))
    game.step()
    zombie = next(iter(game._zombies.values()))
    game._damage(zombie, 1, 123)
    game._clear_dead()
    assert game.observe().counts.defeated == 1


def test_idle_mower_detects_a_crossing_between_samples(make_game):
    def fast(raw):
        raw["zombies"]["basic"]["speed"] = raw["zombies"]["basic"]["max_speed"] = 1000

    game = make_game(
        changes=fast,
        stationary=False,
        mowers=True,
        spawns=(Spawn(1, "basic", 0, x=100),),
    )
    result = game.step()
    assert result.observation.counts.defeated == 1
    assert result.observation.mowers[0].state == "moving"


def test_rising_and_armed_mines_are_not_bite_targets(make_game):
    game = make_game(
        spawns=(Spawn(1, "basic", 0, x=450),),
        plants=(InitialPlant("potato_mine", 0, 0),),
    )
    game.step()
    mine = next(iter(game._plants.values()))
    zombie = next(iter(game._zombies.values()))
    for state in ("rising", "armed"):
        mine.state = state
        assert not game._bite_targets(zombie)
