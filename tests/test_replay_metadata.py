import copy
import json

import pytest

from pvz_game import Game, LevelSpec, Place, Status
from pvz_game.cli import main
from pvz_game.replay import Playback, Recorder


def test_metadata_is_detached_from_callers_and_export():
    game = Game()
    obs = game.reset()
    before = game.state_hash()
    metadata = {
        "policy_id": "shared-v2",
        "checkpoint_sha256": "ab" * 32,
        "experiment": {"scores": [1, 2]},
    }
    recorder = Recorder(game, metadata=metadata)
    metadata["experiment"]["scores"].append(3)
    assert recorder.metadata["experiment"]["scores"] == [1, 2]
    exported = recorder.to_dict()
    exported["metadata"]["experiment"]["scores"].append(4)
    recorder.metadata["experiment"]["scores"].append(5)
    assert recorder.metadata["experiment"]["scores"] == [1, 2]
    assert obs == game.observe()
    assert before == game.state_hash()
    assert "metadata" not in game.snapshot()
    assert not hasattr(game.observe(), "policy_id")


def test_metadata_does_not_change_any_simulation_hash_or_observation(tmp_path):
    a, b = Game(), Game()
    a.reset("standard", 42)
    b.reset("standard", 42)
    plain = Recorder(a, hash_interval=1)
    annotated = Recorder(b, hash_interval=1, metadata={"policy_id": "test", "extra": [None, 1.5]})
    assert plain.step(Place("sunflower", 0, 0), ticks=200) == annotated.step(
        Place("sunflower", 0, 0), ticks=200
    )
    annotated.update_metadata({"outcome": "truncated", "termination_reason": "time_limit"})
    old, new = plain.to_dict(), annotated.to_dict()
    assert "metadata" not in old
    assert {k: v for k, v in new.items() if k != "metadata"} == old
    path = tmp_path / "annotated.json"
    annotated.save(path)
    playback = Playback(path)
    assert playback.display_outcome == "running"  # No future cutoff label on intermediate frames.
    playback.verify()
    assert playback.game.observe().status == Status.RUNNING
    assert playback.display_outcome == "truncated"
    assert playback.game.state_hash() == a.state_hash()
    assert playback.metadata == new["metadata"]


def test_editing_provenance_is_independent_of_simulation_verification():
    game = Game()
    game.reset()
    recorder = Recorder(game, metadata={"policy_id": "original"})
    recorder.step(ticks=20)
    data = recorder.to_dict()
    data["metadata"]["policy_id"] = "different"
    playback = Playback(data)
    assert playback.verify().state_hash() == game.state_hash()
    assert playback.metadata["policy_id"] == "different"
    playback.metadata["policy_id"] = "mutated copy"
    assert playback.metadata["policy_id"] == "different"


@pytest.mark.parametrize(
    "metadata",
    [
        [],
        {"policy_id": 3},
        {"outcome": "unknown"},
        {"termination_reason": None},
        {"checkpoint_sha256": []},
        {"extra": float("nan")},
        {"extra": float("inf")},
        {"nested": {1: "numeric key"}},
        {"extra": (1, 2)},
        {"extra": object()},
    ],
)
def test_invalid_metadata_rejected_atomically(metadata):
    game = Game()
    game.reset()
    recorder = Recorder(game, metadata={"policy_id": "original"})
    before = recorder.to_dict()
    with pytest.raises(ValueError):
        recorder.update_metadata(metadata)
    assert recorder.to_dict() == before
    with pytest.raises(ValueError):
        Recorder(game, metadata=metadata)
    bad = copy.deepcopy(before)
    bad["metadata"] = metadata
    with pytest.raises(ValueError):
        Playback(bad)


def test_cyclic_metadata_rejected():
    metadata = {}
    metadata["cycle"] = metadata
    game = Game()
    game.reset()
    with pytest.raises(ValueError):
        Recorder(game, metadata=metadata)


@pytest.mark.parametrize("outcome", ["truncated", "interrupted", "lost"])
def test_external_label_cannot_replace_engine_victory(outcome):
    game = Game()
    game.reset(LevelSpec("empty"))
    recorder = Recorder(game, metadata={"outcome": outcome})
    recorder.step()
    playback = Playback(recorder.to_dict())
    playback.verify()
    assert playback.display_outcome == "won"


def test_external_metadata_cannot_fabricate_victory():
    game = Game()
    game.reset()
    playback = Playback(Recorder(game, metadata={"outcome": "won"}).to_dict())
    assert playback.display_outcome == "running"


def test_cli_reports_wrapper_outcome_without_replacing_engine_status(tmp_path, capsys):
    game = Game()
    game.reset()
    recorder = Recorder(game, metadata={"outcome": "truncated", "policy_id": "shared"})
    path = tmp_path / "partial.json"
    recorder.save(path)
    assert main(["replay", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "running"
    assert result["outcome"] == "truncated"
    assert result["metadata"]["policy_id"] == "shared"
