import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pvz_game import Dig, Game, InitialPlant, Place
from pvz_game.replay import Playback, Recorder, operation_text


@pytest.fixture
def recorded(make_game):
    game = make_game(plants=(InitialPlant("sunflower", 2, 0),))
    game.step(ticks=13)
    recorder = Recorder(game, hash_interval=1, metadata={"outcome": "truncated"})
    recorder.step(Place("peashooter", 0, 0), ticks=301)
    recorder.step(Place("cherry_bomb", 1, 1), ticks=75)
    recorder.step(Place("sunflower", 2, 0), ticks=30)  # Rejected: occupied.
    recorder.step(Dig(2, 0), ticks=301)
    recorder.step(ticks=201)
    return recorder.to_dict()


def linear_states(data):
    playback = Playback(data)
    states = {playback.current_tick: (playback.game.snapshot(), playback.last_operation)}
    while not playback.done:
        playback.step()
        states[playback.current_tick] = (playback.game.snapshot(), playback.last_operation)
    return states


def test_seek_matches_linear_playback_and_preserves_game_identity(recorded):
    states = linear_states(recorded)
    playback = Playback(recorded)
    game = playback.game
    for tick in (921, 13, 14, 213, 314, 337, 338, 389, 419, 420, 720, 921, 400, 13):
        observation = playback.seek(tick)
        assert observation.tick == tick
        assert playback.game is game
        assert (game.snapshot(), playback.last_operation) == states[tick]
        assert playback.done == (tick == playback.end_tick)
        assert playback.display_outcome == ("truncated" if playback.done else "running")
    playback.seek(390)
    assert "occupied tile" in operation_text(playback.last_operation)


def test_cache_eviction_and_incremental_seek(recorded):
    reference = Playback(recorded).verify().state_hash()
    playback = Playback(recorded)
    playback._cache_limit = 2
    work = playback.seek_steps(playback.end_tick)
    for _ in range(250):
        next(work)
    assert playback.current_tick == playback.start_tick + 250
    assert not playback.done
    for _ in work:
        pass
    assert len(playback._cache) <= 2
    assert playback.game.state_hash() == reference
    playback.seek(playback.start_tick)
    assert playback.game.snapshot() == recorded["initial"]
    assert playback.last_operation is None
    playback.seek(playback.end_tick)
    assert playback.game.state_hash() == reference


@pytest.mark.parametrize("target", [-1, 0, 12, 922, True, 1.5])
def test_invalid_seek_does_not_mutate(recorded, target):
    playback = Playback(recorded)
    before = playback.game.snapshot()
    with pytest.raises(ValueError):
        playback.seek(target)
    assert playback.game.snapshot() == before


@pytest.mark.parametrize("part", ["checkpoint", "final", "action", "gap"])
def test_seek_checks_corrupt_recordings(recorded, part):
    data = copy.deepcopy(recorded)
    if part == "checkpoint":
        data["entries"][1]["state_hash"] = "bad"
    elif part == "final":
        data["final_hash"] = "bad"
    elif part == "action":
        data["entries"][0]["action"]["row"] = 4
    else:
        data["entries"][1]["tick"] += 1
    with pytest.raises(ValueError, match="mismatch"):
        playback = Playback(data)
        playback.seek(playback.end_tick)


@settings(max_examples=12, deadline=None)
@given(st.lists(st.integers(13, 921), min_size=1, max_size=12))
def test_arbitrary_seek_sequences_match_reference(targets):
    game = Game()
    game.reset()
    game.step(ticks=13)
    recorder = Recorder(game, hash_interval=1)
    recorder.step(Place("sunflower", 2, 0), ticks=908)
    data = recorder.to_dict()
    playback = Playback(data)
    for tick in targets:
        reference = Playback(data)
        while reference.current_tick < tick:
            reference.step()
        assert playback.seek(tick) == reference.game.observe()
        assert playback.game.state_hash() == reference.game.state_hash()
