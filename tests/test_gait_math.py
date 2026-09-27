"""Independent rational controls established before changing simulation behavior."""

from fractions import Fraction as F

import pytest


@pytest.mark.parametrize(
    "frames,velocity,expected",
    [
        (47, F(23, 100), F(2209, 16000)),
        (47, F(32, 100), F(2209, 11500)),
        (47, F(45, 100), F(19881, 73600)),
        (37, F(66, 100), F(19129, 48000)),
        (45, F(23, 100), F(9729, 70400)),
    ],
)
def test_continuous_cycle_speed(frames, velocity, expected):
    # Integrate each of N-1 equal-duration ground intervals across one loop.
    distance = F(249, 5) if frames == 47 else F(30) if frames == 37 else F(339, 5)
    fps = velocity * frames / distance * 47
    cycle_seconds = frames / fps
    cycle_pixels = distance * frames / (frames - 1)
    assert cycle_pixels / cycle_seconds / 80 == expected


def test_jump_and_geometry_arithmetic():
    assert -(-4300 // 24) == 180
    # First contact is where the overlap with a 60px plant body reaches 20px.
    for body_x, attack_offset, attack_width in [(36, 14, 20), (115, -65, 70)]:
        overlap = min(body_x + attack_offset + attack_width, 70) - max(body_x + attack_offset, 10)
        assert overlap == 20
        assert (
            min(body_x + 1 + attack_offset + attack_width, 70) - max(body_x + 1 + attack_offset, 10)
            == 19
        )
    # Diagonal circle tangent, one pixel outside, and a same-row mine boundary.
    assert 69**2 + 92**2 == 115**2
    assert 70**2 + 92**2 > 115**2
    assert 60**2 <= 60**2 < 61**2


@pytest.mark.parametrize("gait,speed", [(0, 230), (1, 450), (2, 670), (3, 320)])
@pytest.mark.parametrize("chilled", [False, True])
def test_fixed_point_matches_independent_fraction_integrator(gait, speed, chilled):
    from types import SimpleNamespace

    from pvz_game.mechanics import GAITS, gait_step

    z = SimpleNamespace(gait=gait, speed=speed, gait_phase=0, phase_remainder=0, move_remainder=0)
    deltas = GAITS[gait]
    frames = len(deltas) + 1
    rate = int(F(speed, 1000) * frames * 47 / F(sum(deltas), 10) * 10**6)
    rate //= 2 if chilled else 1
    phase, position, actual = F(0), F(0), 0
    for _ in range(5000):
        index = int(int(phase) * (frames - 1) / 10**6)
        position += F(deltas[index] * rate, 80_000_000)
        actual += gait_step(z, 1000, chilled)
        assert actual == position.numerator // position.denominator
        phase = (phase + F(rate, 100 * frames)) % 10**6
        assert z.gait_phase == int(phase)


@pytest.mark.parametrize("cherry,radius,center", [(True, 115, 40), (False, 60, 20)])
def test_blast_tangent_and_adjacent_lane_controls(cherry, radius, center):
    from pvz_game.mechanics import blast_hits

    # Use 80 units/tile so source pixels and simulation units coincide.
    assert blast_hits(0, 2, center + radius - 1, 2, 80, cherry)
    assert blast_hits(0, 2, center + radius, 2, 80, cherry)
    assert not blast_hits(0, 2, center + radius + 1, 2, 80, cherry)
    assert blast_hits(0, 2, 40, 1, 80, cherry) == cherry
    assert not blast_hits(0, 2, 40, 0, 80, cherry)


def test_mine_trigger_and_blast_are_separate_and_peas_ignore_vault(make_game):
    from pvz_game import InitialPlant, Spawn

    game = make_game(
        spawns=(Spawn(1, "pole_vaulting", 0, x=400), Spawn(5000, "basic", 4)),
        plants=(InitialPlant("potato_mine", 0, 0),),
    )
    game.step()
    mine = next(iter(game._plants.values()))
    zombie = next(iter(game._zombies.values()))
    mine.state = "armed"
    zombie.state = "carrying_pole"
    assert not game._plant_targets(mine)
    zombie.state = "vaulting"
    assert not game._plant_targets(mine)
    assert not game._shot_targets(0, 0, 1000)
    zombie.state = "carrying_pole"
    # Another trigger's explosion CAN damage a grounded carrier.
    game._detonate(mine)
    assert zombie.health == 0


def test_walk_restart_resamples_without_resetting_other_entities(make_game):
    from pvz_game import Dig, InitialPlant, Spawn

    game = make_game(
        stationary=False,
        spawns=(Spawn(1, "basic", 0, x=450), Spawn(10000, "basic", 4)),
        plants=(InitialPlant("wall_nut", 0, 0),),
    )
    game.step(ticks=4)
    z = next(iter(game._zombies.values()))
    assert z.state == "biting"
    state = game._gameplay_rng
    game.step(Dig(0, 0), ticks=4)
    assert z.state == "walking" and game._gameplay_rng != state
    assert 230 <= z.speed <= 320 and z.gait_phase == 0
    snapshot = game.snapshot()
    result = game.step(ticks=333)
    final = game.state_hash()
    game.restore(snapshot)
    assert game.step(ticks=333) == result and game.state_hash() == final
