import pytest

from pvz_game import Dig, InitialPlant, Place, Spawn
from pvz_game.config import PLANT_TYPES, ZOMBIE_TYPES
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


@pytest.mark.parametrize("health", [1, 2])
def test_lethal_custom_one_and_two_hp_bodies_count_once(make_game, health):
    def custom(raw):
        raw["zombies"]["basic"]["health"] = health
        raw["zombies"]["basic"]["max_speed"] = raw["zombies"]["basic"]["speed"] = 0

    game = make_game(changes=custom, spawns=(Spawn(1, "basic", 0, x=2000),))
    game.step()
    zombie = next(iter(game._zombies.values()))
    game._damage(zombie, health, 123)
    game._damage(zombie, health, 123)
    game._clear_dead()
    assert game.observe().counts.defeated == 1
    assert sum(e.kind == "ZombieDefeated" for e in game._events) == 1


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


@pytest.mark.parametrize("state,damage", [("arming", 4), ("rising", 0), ("armed", 0)])
def test_mine_damage_immunity_preserves_bite_target(make_game, state, damage):
    game = make_game(
        spawns=(Spawn(1, "basic", 0, x=450),),
        plants=(InitialPlant("potato_mine", 0, 0),),
    )
    game.step()
    mine = next(iter(game._plants.values()))
    zombie = next(iter(game._zombies.values()))
    mine.state = state
    zombie.age = 3
    before = mine.health
    # Isolate the zombie phase from the mine's independent trigger phase.
    game._advance_zombies()
    assert zombie.state == "biting" and zombie.target_id == mine.id
    assert mine.health == before - damage


@pytest.mark.parametrize("pole,left,right", [(False, -4, 36), (True, 25, 115)])
def test_attack_rectangle_independent_two_sided_boundaries(pole, left, right):
    for x in (left - 1, left, left + 1, right - 1, right, right + 1):
        assert attack_contact(0, x, 80, pole) == (left <= x <= right)


@pytest.mark.parametrize("kind", PLANT_TYPES)
@pytest.mark.parametrize("zombie_kind", ZOMBIE_TYPES)
@pytest.mark.parametrize("col", [2, 3, 4])
def test_planting_ahead_under_and_behind_is_legal(make_game, kind, zombie_kind, col):
    game = make_game(spawns=(Spawn(1, zombie_kind, 0, x=3400), Spawn(100000, "basic", 4)))
    game.step()
    game._cooldowns[kind] = 0
    action = Place(kind, 0, col)
    assert game.validate_action(action).accepted
    assert game.step(action).action_result.accepted


@pytest.mark.parametrize("chilled", [False, True])
@pytest.mark.parametrize("residue", range(8))
def test_bite_acquisition_and_release_only_on_age_cadence(make_game, chilled, residue):
    game = make_game(
        stationary=False,
        spawns=(Spawn(1, "basic", 0, x=3300), Spawn(100000, "basic", 4)),
        plants=(InitialPlant("wall_nut", 0, 3),),
    )
    game.step()
    z = next(iter(game._zombies.values()))
    p = next(iter(game._plants.values()))
    z.age = residue
    z.slow_until = 1000 if chilled else 0
    period = 8 if chilled else 4
    x, hp = z.x, p.health
    game.step()
    acquired = (residue + 1) % period == 0
    assert z.x < x  # movement precedes acquisition, never clamps to an edge
    assert (z.state == "biting") == acquired
    assert p.health == hp - (4 if acquired else 0)
    while z.state != "biting":
        game.step()
    x, phase = z.x, z.gait_phase
    for _ in range(period - 1):
        game.step()
        assert z.x == x and z.gait_phase == phase
    # Remove just before cadence. It releases now and walks next tick.
    game.step(Dig(0, 3))
    assert z.state == "walking" and z.x == x
    game.step()
    assert z.x < x


@pytest.mark.parametrize(
    "x,contact",
    [(2949, False), (2950, True), (2951, True), (3449, True), (3450, True), (3451, False)],
)
def test_bite_contact_boundaries_and_lane_isolation(make_game, x, contact):
    game = make_game(
        spawns=(Spawn(1, "basic", 0, x=x), Spawn(1, "basic", 1, x=x)),
        plants=(InitialPlant("wall_nut", 0, 3),),
    )
    game.step(ticks=4)
    zombies = list(game._zombies.values())
    assert (zombies[0].state == "biting") == contact
    assert zombies[1].state == "walking"
    assert game.observe().plants[0].health == 4000 - (4 if contact else 0)


def test_already_passed_attack_interval_keeps_walking(make_game):
    game = make_game(
        stationary=False,
        spawns=(Spawn(1, "basic", 0, x=2949),),
        plants=(InitialPlant("wall_nut", 0, 3),),
    )
    game.step(ticks=16)
    z = next(iter(game._zombies.values()))
    assert z.x < 2949 and z.state == "walking"
    assert game.observe().plants[0].health == 4000


@pytest.mark.parametrize("biting", [False, True])
def test_headless_preserves_locomotion_without_biting_or_double_count(make_game, biting):
    game = make_game(
        stationary=False,
        spawns=(Spawn(1, "basic", 0, x=3300), Spawn(100000, "basic", 4)),
        plants=(InitialPlant("wall_nut", 0, 3),) if biting else (),
    )
    game.step(ticks=4)
    z = next(iter(game._zombies.values()))
    game._damage(z, 190, 123)
    assert z.headless and game.observe().counts.defeated == 1
    x = z.x
    game.step(ticks=4)
    assert (z.x == x) if biting else (z.x < x)
    if biting:
        assert game.observe().plants[0].health == 3996
    game._damage(z, 9999, 123)
    assert game.observe().counts.defeated == 1


@pytest.mark.parametrize("units", [80, 1000, 2000])
def test_coordinate_resolution_does_not_change_velocity_units(make_game, units):
    from fractions import Fraction

    game = make_game(
        stationary=False,
        spawns=(Spawn(1, "basic", 0, x=8 * units),),
        changes=lambda raw: raw["game"].update(
            units_per_tile=units, mower_speed=4, projectile_speed=4
        ),
    )
    game.step(ticks=100)
    z = next(iter(game._zombies.values()))
    assert 230 <= z.speed <= 320
    # Independent bounds from the reference velocity, allowing gait variation.
    distance = Fraction(8 * units - z.x, units)
    assert Fraction(1, 20) < distance < Fraction(1, 2)


@pytest.mark.parametrize("delta,hit", [(-1, False), (0, False), (1, True)])
def test_zombie_sweep_projectile_tangency_and_adjacent_lane(make_game, delta, hit):
    from pvz_game.engine import _Projectile

    game = make_game(spawns=(Spawn(1, "basic", 0, x=0), Spawn(100000, "basic", 4)))
    game.step()
    z = next(iter(game._zombies.values()))
    # Pea right edge q+40*1000/80 = 1100 at delta=0.
    shot = _Projectile(game._id(), 0, 600 + delta, 20, False)
    other = _Projectile(game._id(), 1, 600 + delta, 20, False)
    game._projectiles.update({shot.id: shot, other.id: other})
    z.x = 1200
    game._move_zombie(z, 1100)
    assert (shot.id not in game._projectiles) == hit
    assert other.id in game._projectiles


def test_pole_checks_before_moving_and_ignores_new_plants_in_flight(make_game):
    game = make_game(
        stationary=False,
        spawns=(Spawn(1, "pole_vaulting", 0, x=4438), Spawn(100000, "basic", 4)),
        plants=(InitialPlant("wall_nut", 0, 3),),
    )
    first = game.step()
    z = next(iter(game._zombies.values()))
    assert z.x < 4438 and z.state == "carrying_pole"
    assert not any(e.kind == "VaultStarted" for e in first.events)
    second = game.step()
    assert z.state == "vaulting"
    assert sum(e.kind == "VaultStarted" for e in second.events) == 1
    landing = z.landing_x
    game.step(Dig(0, 3))
    game._cooldowns["sunflower"] = 0
    assert game.step(Place("sunflower", 0, 2)).action_result.accepted
    assert z.state == "vaulting" and z.landing_x == landing
    result = game.step(ticks=180)
    assert not z.has_pole and z.state != "vaulting"
    assert sum(e.kind == "VaultFinished" for e in result.events) == 1


def test_removed_target_is_released_on_next_cadence_without_early_motion(make_game):
    game = make_game(
        stationary=False,
        spawns=(Spawn(1, "basic", 0, x=3300),),
        plants=(InitialPlant("wall_nut", 0, 3),),
    )
    game.step(ticks=4)
    z = next(iter(game._zombies.values()))
    x = z.x
    game.step(Dig(0, 3))
    assert z.state == "biting" and z.x == x
    game.step(ticks=3)
    assert z.state == "walking" and z.x == x
    game.step()
    assert z.x < x
