from dataclasses import FrozenInstanceError, asdict

import pytest

from pvz_game import (
    Dig,
    Game,
    GameFinishedError,
    InitialPlant,
    LevelSpec,
    Place,
    Spawn,
    Status,
    Wait,
)


def test_economy_exact_cost_and_cooldown(make_game):
    game = make_game(sun=50)
    result = game.step(Place("sunflower", 0, 0))
    assert result.action_result.accepted
    assert result.observation.sun == 0
    assert result.observation.cards[0].cooldown_ticks == 149
    assert not game.step(Place("sunflower", 0, 1)).action_result.accepted
    game.step(ticks=117)
    assert game.observe().sun == 0  # First sunflower income at exactly tick 120.
    game.step()
    assert game.observe().sun == 25
    game.step(ticks=30)
    assert game.observe().cards[0].cooldown_ticks == 0
    assert game.validate_action(Place("sunflower", 0, 1)).reason == "insufficient_sun"
    game.step(ticks=50)
    assert game.observe().sun == 50
    assert game.step(Place("sunflower", 0, 1)).action_result.accepted


def test_one_sun_short_is_rejected_without_charging(make_game):
    game = make_game(sun=99)
    result = game.step(Place("peashooter", 0, 0), ticks=2)
    assert result.action_result.reason == "insufficient_sun"
    assert result.ticks_advanced == 2
    assert result.observation.sun == 99
    assert result.observation.cards[1].cooldown_ticks == 0
    assert not result.observation.plants


@pytest.mark.parametrize("row,col", [(0, 0), (0, 8), (4, 0), (4, 8)])
def test_all_board_corners_and_digging(make_game, row, col):
    game = make_game()
    assert game.step(Place("peashooter", row, col)).action_result.accepted
    before = game.observe().sun
    assert game.step(Place("sunflower", row, col)).action_result.reason == "occupied_tile"
    assert game.step(Dig(row, col)).action_result.accepted
    assert game.observe().sun == before
    assert game.step(Dig(row, col)).action_result.reason == "empty_tile"
    assert game.step(Place("peashooter", row, col)).action_result.reason == "card_recharging"
    assert game.step(Place("sunflower", row, col)).action_result.accepted


@pytest.mark.parametrize(
    "action,reason",
    [
        (Place("peashooter", -1, 0), "outside_board"),
        (Place("peashooter", 5, 0), "outside_board"),
        (Dig(0, 9), "outside_board"),
        (Place("invented", 0, 0), "unknown_plant"),
    ],
)
def test_invalid_gameplay_actions_advance_time(make_game, action, reason):
    game = make_game()
    result = game.step(action, ticks=3)
    assert result.action_result.reason == reason
    assert result.observation.tick == 3
    assert result.observation.sun == 9990


@pytest.mark.parametrize(
    "action,ticks",
    [(None, 1), (Place("sunflower", 1.5, 0), 1), (Wait(), 0), (Wait(), True), (Wait(), 1.5)],
)
def test_malformed_requests_are_atomic(make_game, action, ticks):
    game = make_game()
    before = game.state_hash()
    with pytest.raises((TypeError, ValueError)):
        game.step(action, ticks=ticks)
    assert game.state_hash() == before


def test_sun_production_matches_independent_arithmetic(make_game):
    game = make_game(sun=0, plants=(InitialPlant("sunflower", 0, 0),))
    game.step(ticks=2000)
    # 100 seconds: sky at 10..100; sunflower at 6,30,54,78.
    assert game.observe().sun == 10 * 25 + 4 * 25
    capped = make_game(sun=9990, plants=(InitialPlant("sunflower", 0, 0),))
    result = capped.step(ticks=200)
    assert result.observation.sun == 9990
    assert all(e.get("amount") == 0 for e in result.events if e.kind == "SunProduced")


def test_ten_peas_kill_200_hp_at_analytical_tick(make_game):
    game = make_game(
        spawns=(Spawn(1, "basic", 0, x=1000),), plants=(InitialPlant("peashooter", 0, 0),)
    )
    game.step(ticks=270)
    assert game.observe().zombies[0].health == 20
    result = game.step()
    assert result.observation.tick == 1 + 9 * 30
    assert result.status == Status.WON
    assert result.observation.counts.defeated == 1


def test_nearest_target_lane_isolation_and_swept_projectile(make_game):
    def speed(raw):
        raw["game"]["projectile_speed"] = 200

    game = make_game(
        spawns=(
            Spawn(1, "basic", 0, x=4000),
            Spawn(1, "basic", 0, x=2000),
            Spawn(1, "basic", 1, x=1000),
        ),
        plants=(InitialPlant("peashooter", 0, 0),),
        changes=speed,
    )
    game.step()
    by_x = {z.x: z.health for z in game.observe().zombies}
    assert by_x == {4000: 200, 2000: 180, 1000: 200}


def test_armor_absorbs_and_excess_reaches_health(make_game):
    def damage(raw):
        raw["plants"]["peashooter"]["damage"] = 450

    game = make_game(
        spawns=(Spawn(1, "conehead", 0, x=1000),),
        plants=(InitialPlant("peashooter", 0, 0),),
        changes=damage,
    )
    game.step()
    z = game.observe().zombies[0]
    assert (z.armor, z.health) == (0, 150)


def test_repeater_burst_has_exact_spacing(make_game):
    game = make_game(
        spawns=(Spawn(1, "buckethead", 0, x=1000),), plants=(InitialPlant("repeater", 0, 0),)
    )
    results = [game.step() for _ in range(34)]
    fired = [e.tick for r in results for e in r.events if e.kind == "ProjectileFired"]
    assert fired == [1, 4, 31, 34]


def test_simultaneous_hits_do_not_double_count_death(make_game):
    def damage(raw):
        raw["plants"]["peashooter"]["damage"] = 200
        raw["game"]["projectile_speed"] = 200

    game = make_game(
        spawns=(Spawn(1, "basic", 0, x=4000),),
        plants=(InitialPlant("peashooter", 0, 0), InitialPlant("peashooter", 0, 1)),
        changes=damage,
    )
    result = game.step()
    assert sum(e.kind == "ZombieDefeated" for e in result.events) == 1
    assert result.observation.counts.defeated == 1


def test_bomb_fuse_and_half_open_area_boundaries(make_game):
    game = make_game(
        spawns=(
            Spawn(1, "basic", 1, x=2000),
            Spawn(1, "basic", 3, x=4999),
            Spawn(1, "basic", 2, x=5000),
            Spawn(1, "basic", 0, x=3500),
        ),
        plants=(InitialPlant("cherry_bomb", 2, 3),),
    )
    game.step(ticks=23)
    assert game.observe().counts.alive == 4
    result = game.step()
    assert result.observation.counts.defeated == 2
    assert {z.x for z in result.observation.zombies} == {5000, 3500}
    assert not result.observation.plants


def test_mine_arms_exactly_and_detonates_before_vault(make_game):
    game = make_game(
        spawns=(Spawn(279, "pole_vaulting", 0, x=1800),),
        plants=(InitialPlant("potato_mine", 0, 1),),
    )
    game.step(ticks=278)
    assert game.observe().plants[0].state == "arming"
    # Tick 279 starts the pole's vault; tick 280 mine triggers during its delay.
    game.step()
    result = game.step()
    assert result.status == Status.WON
    assert any(e.kind == "MineArmed" for e in result.events)
    assert result.observation.counts.defeated == 1


def test_unarmed_mine_can_be_eaten(make_game):
    game = make_game(
        spawns=(Spawn(1, "basic", 0, x=1800),), plants=(InitialPlant("potato_mine", 0, 1),)
    )
    game.step(ticks=60)
    assert not game.observe().plants
    assert game.observe().counts.defeated == 0


def test_chomper_ignores_armor_and_digests(make_game):
    game = make_game(
        spawns=(Spawn(1, "buckethead", 0, x=1000), Spawn(1, "pole_vaulting", 0, x=1400)),
        plants=(InitialPlant("chomper", 0, 0),),
    )
    game.step()
    assert game.observe().counts.defeated == 1
    assert game.observe().plants[0].state == "digesting"
    game.step(ticks=839)
    assert game.observe().counts.defeated == 1
    result = game.step()
    assert result.status == Status.WON
    assert result.observation.counts.defeated == 2


def test_slow_halves_movement_and_expires_without_stacking(make_game):
    game = make_game(
        stationary=False,
        spawns=(Spawn(1, "buckethead", 0, x=3000),),
        plants=(InitialPlant("snow_pea", 0, 0),),
    )
    game.step(ticks=6)
    z = game.observe().zombies[0]
    assert z.slow_ticks > 0
    # Remove the source so expiration can be measured without refreshing.
    game.step(Dig(0, 0))
    before = game.observe().zombies[0]
    game.step(ticks=20)
    after = game.observe().zombies[0]
    assert before.x - after.x == 100  # .1 tiles / second = half ordinary speed.
    remaining = after.slow_ticks
    game.step(ticks=remaining)
    before = game.observe().zombies[0]
    assert before.slow_ticks == 0
    game.step(ticks=20)
    assert before.x - game.observe().zombies[0].x == 200


def test_slow_refreshes_and_halves_biting(make_game):
    game = make_game(
        spawns=(Spawn(1, "buckethead", 0, x=800),), plants=(InitialPlant("snow_pea", 0, 0),)
    )
    game.step(ticks=39)
    assert game.observe().plants[0].health == 300
    assert game.observe().zombies[0].slow_ticks > 170  # Refreshed by second pea.
    game.step()
    assert game.observe().plants[0].health == 200


def test_pole_vaults_once_and_then_bites(make_game):
    game = make_game(
        stationary=False,
        spawns=(Spawn(1, "pole_vaulting", 0, x=3900),),
        plants=(InitialPlant("wall_nut", 0, 3), InitialPlant("wall_nut", 0, 1)),
    )
    result = game.step(ticks=300)
    assert sum(e.kind == "VaultStarted" for e in result.events) == 1
    assert not result.observation.zombies[0].has_pole
    assert result.observation.zombies[0].state == "biting"
    assert next(p for p in result.observation.plants if p.col == 3).health == 4000
    assert next(p for p in result.observation.plants if p.col == 1).health < 4000


def test_removing_vault_target_does_not_change_landing(make_game):
    game = make_game(
        stationary=False,
        spawns=(Spawn(1, "pole_vaulting", 0, x=1800),),
        plants=(InitialPlant("wall_nut", 0, 1),),
    )
    game.step()
    assert game.observe().zombies[0].state == "vaulting"
    game.step(Dig(0, 1), ticks=16)
    z = game.observe().zombies[0]
    assert z.state == "walking"
    assert z.x == 790  # Lands at .8 tiles, then walks one normal tick.


def test_mower_catches_simultaneous_crossings_but_later_arrival_loses(make_game):
    game = make_game(
        stationary=False,
        mowers=True,
        spawns=(
            Spawn(1, "basic", 0, x=0),
            Spawn(1, "buckethead", 0, x=0),
            Spawn(100, "basic", 0, x=0),
        ),
    )
    first = game.step()
    assert first.observation.counts.defeated == 2
    assert sum(e.kind == "MowerActivated" for e in first.events) == 1
    game.step(ticks=200)
    assert game.observe().status == Status.LOST
    assert game.observe().counts.remaining == 1


def test_no_early_victory_and_spawn_death_counters(make_game):
    def damage(raw):
        raw["plants"]["peashooter"]["damage"] = 200

    game = make_game(
        spawns=(Spawn(1, "basic", 0, x=1000), Spawn(100, "basic", 0, x=1000)),
        plants=(InitialPlant("peashooter", 0, 0),),
        changes=damage,
    )
    result = game.step()
    counts = result.observation.counts
    assert (
        counts.initial_total,
        counts.spawned,
        counts.alive,
        counts.defeated,
        counts.not_yet_spawned,
        counts.remaining,
    ) == (2, 1, 0, 1, 1, 1)
    game.step(ticks=98)
    assert game.observe().status == Status.RUNNING
    final = game.step(ticks=100)
    assert final.ticks_advanced == 1
    assert final.status == Status.WON
    with pytest.raises(GameFinishedError):
        game.step()
    assert game.legal_actions() == ()


def test_empty_level_ends_on_first_tick(make_game):
    game = make_game(spawns=())
    assert game.step(ticks=10).ticks_advanced == 1
    assert game.observe().status == Status.WON


def test_observations_are_immutable_and_do_not_reveal_future():
    game = Game()
    obs = game.reset("standard", 42)
    assert not obs.zombies
    assert obs.counts.not_yet_spawned == 40
    assert "spawns" not in asdict(obs)
    with pytest.raises(FrozenInstanceError):
        obs.sun = 10000


def test_invalid_reset_preserves_existing_game(make_game):
    game = make_game()
    before = game.state_hash()
    with pytest.raises(ValueError):
        game.reset(LevelSpec("bad", (Spawn(0, "basic", 8),)))
    assert game.state_hash() == before
