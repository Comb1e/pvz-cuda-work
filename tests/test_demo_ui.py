import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pytest

pygame = pytest.importorskip("pygame")

from pvz_game import Game, InitialPlant, Place, Spawn, Wait  # noqa: E402
from pvz_game.demo import DemoCancelled, DemoSession, generate_demo  # noqa: E402
from pvz_game.demo_ui import LivePreview  # noqa: E402
from pvz_game.replay import Playback, Recorder  # noqa: E402
from pvz_game.ui import App, Screen  # noqa: E402


class Clock:
    def tick(self, fps):
        return 50  # Controlled wall clock; tests never sleep.


@pytest.fixture(autouse=True)
def display_lifecycle(monkeypatch):
    pygame.quit()
    monkeypatch.setattr(pygame.time, "Clock", Clock)
    yield
    pygame.quit()


@pytest.mark.parametrize("speed", [0.5, 1, 2, 4, 8])
def test_live_and_headless_preserve_results_entries_events_and_bytes(tmp_path, make_game, speed):
    games = [
        make_game(
            plants=(InitialPlant("sunflower", 2, 0),),
            spawns=(Spawn(1, "basic", 0, x=3000), Spawn(100000, "basic", 4)),
        )
        for _ in range(3)
    ]
    operations = [(Place("peashooter", 0, 0), 13), (Place("peashooter", 0, 0), 7), (Wait(), 180)]
    expected = [games[0].step(action, ticks=ticks) for action, ticks in operations]
    recorded = []
    for index, live in enumerate((False, True), 1):
        path = tmp_path / f"{live}.pvzdemo"
        with DemoSession(games[index], output=path, live=live, speed=speed) as session:
            actual = [session.step(action, ticks=ticks) for action, ticks in operations]
            assert actual == expected
        assert games[index].state_hash() == games[0].state_hash()
        assert len(session.recorder.entries) == 3
        recorded.append(path.read_bytes())
    assert recorded[0] == recorded[1]


@pytest.mark.parametrize("cancel_at", [0, 3])
def test_live_cancellation_saves_only_completed_ticks(tmp_path, monkeypatch, cancel_at):
    game = Game()
    game.reset()
    path = tmp_path / "cancelled.pvzdemo"
    with DemoSession(game, output=path, live=True) as session:
        preview = session._preview
        after = preview.after_tick

        def completed(result, action):
            after(result, action)
            if result.observation.tick == cancel_at:
                pygame.event.post(pygame.event.Event(pygame.QUIT))

        monkeypatch.setattr(preview, "after_tick", completed)
        if cancel_at == 0:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
        with pytest.raises(DemoCancelled):
            session.step(Place("sunflower", 2, 0), ticks=100)
        assert preview.closed
    playback = Playback(path)
    assert playback.end_tick == cancel_at
    assert len(playback.data["entries"]) == (1 if cancel_at else 0)
    assert playback.verify().state_hash() == game.state_hash()
    assert playback.display_outcome == "interrupted"
    assert playback.metadata["termination_reason"] == "window_closed"


def test_generator_returns_interrupted_result_on_close(tmp_path, monkeypatch):
    after = LivePreview.after_tick

    def completed(self, result, action):
        after(self, result, action)
        if result.observation.tick == 4:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    monkeypatch.setattr(LivePreview, "after_tick", completed)
    result = generate_demo(output=tmp_path / "cancelled.pvzdemo", live=True, max_ticks=200)
    assert result.outcome == "interrupted" and result.ticks_recorded == 4
    assert Playback(result.path).verify().state_hash() == result.final_hash


def test_live_pause_step_resume_and_speed_controls(tmp_path):
    game = Game()
    game.reset()
    with DemoSession(game, output=tmp_path / "live.pvzdemo", live=True) as session:
        preview = session._preview
        preview.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        assert preview.paused
        assert game.observe().tick == 0
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PERIOD))
        session.step()
        assert preview.paused and game.observe().tick == 1
        preview.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        for expected in (2, 4, 8, 0.5, 1):
            preview.handle_event(
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=preview.speed_rect.center)
            )
            assert preview.speed == expected
        session.step(ticks=2)
        assert game.observe().tick == 3


@pytest.fixture
def replay_app(tmp_path):
    game = Game()
    game.reset()
    recorder = Recorder(game, metadata={"outcome": "truncated", "termination_reason": "sample_end"})
    recorder.step(Place("sunflower", 2, 0), ticks=600)
    recorder.step(Place("sunflower", 2, 0), ticks=200)
    path = tmp_path / "replay.pvzdemo"
    recorder.save(path)
    return App(replay_path=path)


def finish_seek(app):
    frames = 0
    while app.mode == Screen.SEEKING:
        app.update(0)
        frames += 1
        assert frames < 20


def test_timeline_pauses_during_drag_and_restores_previous_mode(replay_app):
    app = replay_app
    initial = app.game
    rect = app.timeline_rect()
    app.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(rect.centerx, rect.centery))
    )
    assert app.mode == Screen.SEEKING
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    finish_seek(app)
    assert app.mode == Screen.PAUSED and app.playback.current_tick == 400
    app.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(rect.centerx, rect.centery))
    )
    finish_seek(app)
    assert app.mode == Screen.PLAYING
    assert app.game is initial


def test_long_seek_is_bounded_and_completion_stays_seekable(replay_app):
    app = replay_app
    app.effects = [(1000, 2, 0, 1)]
    app.sun_flash_until = 1000
    app.request_seek(800)
    app.update(0)
    assert app.mode == Screen.SEEKING
    assert app.playback.current_tick <= app.demo_settings["seek_chunk_ticks"]
    finish_seek(app)
    assert app.mode == Screen.ENDED
    assert not app.effects and app.sun_flash_until == 0
    app.draw()
    assert "speed" in app.buttons and "restart" in app.buttons
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT))
    finish_seek(app)
    assert app.playback.current_tick == 300 and app.mode == Screen.PAUSED
    assert app.playback.display_outcome == "running"
    assert "accepted" in app.message
    app.request_seek(700)
    finish_seek(app)
    assert "occupied tile" in app.message
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_HOME))
    finish_seek(app)
    assert app.playback.current_tick == 0
    assert app.playback.last_operation is None
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PERIOD))
    assert app.playback.current_tick == 1
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_END))
    finish_seek(app)
    assert app.mode == Screen.ENDED
    app.restart()
    assert app.mode == Screen.PLAYING and app.playback.current_tick == 0


@pytest.mark.parametrize("speed", [0.5, 1, 2, 4, 8])
def test_viewer_speed_changes_pacing_only(replay_app, speed):
    app = replay_app
    app.speed = speed
    for _ in range(10000):
        if app.mode == Screen.ENDED:
            break
        app.update(1 / 60)
    assert app.mode == Screen.ENDED
    assert app.game.state_hash() == app.playback.data["final_hash"]


def test_ui_cycles_full_replay_speed_set(replay_app):
    for expected in (2, 4, 8, 0.5, 1):
        replay_app.activate("speed")
        assert replay_app.speed == expected


@pytest.mark.parametrize("speed,expected", [(0.5, 2), (8, 2), (2, 4)])
def test_returning_from_replay_preserves_valid_human_speed_controls(replay_app, speed, expected):
    app = replay_app
    app.speed = speed
    app.activate("menu")
    app.activate("level:easy")
    assert app.playback is None and app.mode == Screen.PLAYING
    app.activate("speed")
    assert app.speed == expected
