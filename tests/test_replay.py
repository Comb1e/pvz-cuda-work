import copy
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pvz_game import Game, Place, Status
from pvz_game.replay import Playback, Recorder, verify_replay


def test_reset_seed_and_instances_are_isolated():
    a, b = Game(), Game()
    a.reset("hard", 42)
    b.reset("hard", 42)
    initial = a.state_hash()
    assert b.state_hash() == initial
    a.step(Place("sunflower", 0, 0), ticks=700)
    assert b.state_hash() == initial
    b.step(Place("sunflower", 0, 0), ticks=700)
    assert a.state_hash() == b.state_hash()
    a.reset("hard", 42)
    assert a.state_hash() == initial
    a.reset("hard", 43)
    assert a.snapshot()["level"]["spawns"] != b.snapshot()["level"]["spawns"]


def test_snapshot_json_roundtrip_restores_every_timer(make_game):
    game = make_game()
    game.step(Place("potato_mine", 1, 2), ticks=100)
    game.step(Place("cherry_bomb", 2, 2), ticks=4)
    snapshot = json.loads(json.dumps(game.snapshot()))
    initial_hash = game.state_hash()
    result_a = game.step(ticks=220)
    final_hash = game.state_hash()
    game.restore(snapshot)
    assert game.state_hash() == initial_hash
    result_b = game.step(ticks=220)
    assert result_a == result_b
    assert game.state_hash() == final_hash


@pytest.mark.parametrize(
    "field,value",
    [
        ("snapshot_version", 99),
        ("engine_version", "0.0"),
        ("sun", -1),
        ("spawn_index", 1),
        ("next_id", 0),
    ],
)
def test_bad_snapshot_rejected_atomically(make_game, field, value):
    game = make_game()
    before = game.state_hash()
    snapshot = game.snapshot()
    snapshot[field] = value
    with pytest.raises(ValueError):
        game.restore(snapshot)
    assert game.state_hash() == before


def test_snapshot_is_detached_and_rules_must_match(make_game):
    game = make_game()
    snapshot = game.snapshot()
    snapshot["cooldowns"]["sunflower"] = 50
    assert game.observe().cards[0].cooldown_ticks == 0
    snapshot["rules"]["plants"]["sunflower"]["cost"] = 1
    with pytest.raises(ValueError, match="rules"):
        game.restore(snapshot)


def test_recording_verifies_chunked_steps_and_tampering(tmp_path):
    game = Game()
    game.reset("standard", 42)
    recorder = Recorder(game, hash_interval=2)
    recorder.step(Place("sunflower", 0, 0), ticks=200)
    recorder.step(Place("sunflower", 1, 0), ticks=200)
    recorder.step(ticks=400)
    path = tmp_path / "replay.json"
    recorder.save(path)
    assert verify_replay(path).state_hash() == game.state_hash()
    data = recorder.to_dict()
    data["entries"][0]["action"]["row"] = 2
    with pytest.raises(ValueError, match="mismatch"):
        verify_replay(data)


def test_empty_recording_and_final_hash_check():
    game = Game()
    game.reset()
    data = Recorder(game).to_dict()
    playback = Playback(data)
    assert playback.done
    data["final_hash"] = "tampered"
    with pytest.raises(ValueError, match="mismatch"):
        Playback(data)


@settings(max_examples=15, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(0, 4), st.integers(0, 8), st.integers(1, 40)), min_size=1, max_size=20
    )
)
def test_chunking_does_not_change_simulation(actions):
    a, b = Game(), Game()
    a.reset("standard", 5)
    b.reset("standard", 5)
    for row, col, ticks in actions:
        action = Place("sunflower", row, col)
        a.step(action, ticks=ticks)
        b.step(action)
        for _ in range(ticks - 1):
            b.step()
    assert a.state_hash() == b.state_hash()


@pytest.mark.parametrize("name", ["easy", "standard", "hard"])
def test_shipped_winning_playthrough(name):
    path = Path(__file__).parent / "fixtures" / "v16" / f"{name}-seed42.json"
    assert path.exists(), f"missing acceptance fixture: {path}"
    final = verify_replay(path)
    assert final.observe().status == Status.WON
    assert final.observe().counts.remaining == 0


def test_restored_order_and_events_match(make_game):
    game = make_game()
    game.step(Place("sunflower", 0, 0), ticks=160)
    checkpoint = copy.deepcopy(game.snapshot())
    a = game.step(Place("sunflower", 1, 0), ticks=500)
    game.restore(checkpoint)
    b = game.step(Place("sunflower", 1, 0), ticks=500)
    assert a == b
