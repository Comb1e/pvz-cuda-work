"""Portable research-timeline fixtures; no research or Torch import required."""

import copy

import pytest

from pvz_game import Dig, Game, LevelSpec, Place, Spawn, Wait
from pvz_game.action_replay import ActionPhaseGame
from pvz_game.replay import Playback, Recorder, action_dict, write_recording


def demo(operations, *, mowers=True, spawn_tick=1000, start=0):
    game = ActionPhaseGame()
    game.reset(
        LevelSpec("fixture", (Spawn(spawn_tick, "basic", 0, x=0),), initial_sun=500, mowers=mowers),
        9,
    )
    if start:
        game.step(ticks=start)
    initial, entries = game.snapshot(), []
    expected = {game.observe().tick: game.state_hash()}
    for action, ticks in operations:
        tick = game.observe().tick
        result = game.step(action, ticks=ticks)
        entries.append(
            dict(
                tick=tick,
                ticks=result.ticks_advanced,
                action=action_dict(action),
                state_hash=game.state_hash(),
            )
        )
        expected[game.observe().tick] = game.state_hash()
    return dict(
        replay_version="pvz-rl/actions-v1",
        initial=initial,
        entries=entries,
        final_hash=game.state_hash(),
        final_status=game.observe().status.value,
        metadata={"outcome": "truncated", "checkpoint_sha256": "fixture"},
    ), expected


@pytest.mark.parametrize("suffix", [".pvzdemo", ".json.gz", ".json"])
def test_native_loader_preserves_zero_actions_batches_seek_and_hash(tmp_path, suffix):
    data, states = demo(
        [
            (Place("peashooter", 0, 0), 0),
            (Place("sunflower", 1, 0), 0),
            (Wait(), 100),
            (Dig(1, 0), 0),
            (Wait(), 3),
            (Place("wall_nut", 1, 1), 0),
        ],
        start=7,
    )
    path = tmp_path / ("replay" + suffix)
    write_recording(data, path)
    playback = Playback(path)
    assert playback.game.observe().tick == 7
    assert len(playback.game.observe().plants) == 2
    identity = id(playback.game)
    playback.verify()
    for tick in (7, 107, 108, 110, 107, 7, 110):
        playback.seek(tick)
        assert id(playback.game) == identity
        if tick in states:
            assert playback.game.state_hash() == states[tick]
        assert playback.done == (tick == 110)
    assert playback.display_outcome == "truncated"
    assert playback.metadata["checkpoint_sha256"] == "fixture"


@pytest.mark.parametrize("mowers,outcome", [(True, "won"), (False, "lost")])
def test_natural_outcome_overrides_external_cutoff(mowers, outcome):
    data, _ = demo([(Place("sunflower", 1, 0), 0), (Wait(), 500)], mowers=mowers, spawn_tick=1)
    player = Playback(data)
    player.verify()
    assert player.display_outcome == outcome
    player.seek(0)
    assert not player.done and player.display_outcome == "running"
    player.verify()
    assert player.display_outcome == outcome


def test_instant_only_recording_and_corruption():
    data, _ = demo([(Place("sunflower", 1, 0), 0), (Dig(1, 0), 0)])
    player = Playback(data)
    assert player.done and player.end_tick == player.start_tick == 0
    assert not player.game.observe().plants
    for mutate in (
        lambda d: d.update(final_hash="bad"),
        lambda d: d["entries"][0].update(state_hash="bad"),
        lambda d: d["entries"][0].update(ticks=-1),
        lambda d: d["entries"][0].update(action={"kind": "wait"}),
        lambda d: d["entries"][1].update(tick=1),
        lambda d: d.update(replay_version="unknown-future"),
    ):
        corrupt = copy.deepcopy(data)
        mutate(corrupt)
        with pytest.raises(ValueError):
            Playback(corrupt).verify()


def test_ordinary_recorder_and_game_api_keep_positive_time_contract():
    game = Game()
    game.reset("easy", 0)
    with pytest.raises(ValueError):
        game.step(Place("sunflower", 0, 0), ticks=0)
    recorder = Recorder(game)
    recorder.step(Place("sunflower", 0, 0), ticks=2)
    assert recorder.to_dict()["replay_version"] == 1
    player = Playback(recorder.to_dict())
    assert type(player) is Playback
    assert player.verify().state_hash() == game.state_hash()


def test_native_viewer_opens_and_draws_research_recording(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    pygame = pytest.importorskip("pygame")
    from pvz_game.ui import App

    data, _ = demo([(Place("peashooter", 1, 0), 0), (Wait(), 3)])
    app = App(replay_path=data, speed=2)
    try:
        before = app.game.state_hash()
        app.draw()
        assert app.game.state_hash() == before
        app.playback.seek(app.playback.end_tick)
        assert app.playback.display_outcome == "truncated"
        app.draw()
        assert app.game.state_hash() == data["final_hash"]
    finally:
        pygame.quit()
