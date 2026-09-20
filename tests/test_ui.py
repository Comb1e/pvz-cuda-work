import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pytest

pygame = pytest.importorskip("pygame")

from pvz_game import Place  # noqa: E402
from pvz_game.ui import App, Screen  # noqa: E402


@pytest.fixture
def app():
    app = App(level="standard", seed=42)
    yield app
    pygame.quit()


def test_rendering_does_not_change_simulation(app):
    app.game.step(Place("sunflower", 0, 0), ticks=200)
    before = app.game.state_hash()
    for _ in range(5):
        app.draw()
    assert app.game.state_hash() == before


def test_human_clicks_use_same_game_api(app):
    app.draw()
    app.activate("card:sunflower")
    pos = (app.cfg["board_x"] + 10, app.cfg["board_y"] + 10)
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    app.advance()
    assert app.game.observe().plants[0].plant_type == "sunflower"
    assert app.game.observe().sun == 0
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    app.advance()
    assert app.message == "Occupied tile."


def test_pause_single_step_restart_and_menu(app):
    initial = app.game.state_hash()
    app.toggle_pause()
    assert app.mode == Screen.PAUSED
    app.draw()
    assert app.game.state_hash() == initial
    app.activate("step")
    assert app.game.observe().tick == 1
    assert app.mode == Screen.PAUSED
    app.restart()
    assert app.game.state_hash() == initial
    app.activate("menu")
    assert app.mode == Screen.MENU
    app.draw()


def test_keyboard_and_shovel(app):
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1, unicode="1"))
    assert app.selected == "sunflower"
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode=""))
    assert app.selected is None
    assert app.mode == Screen.PLAYING
    app.activate("shovel")
    assert app.selected == "shovel"
    app.activate("speed")
    assert app.speed == 2
    app.activate("speed")
    assert app.speed == 4
    app.activate("speed")
    assert app.speed == 1


def test_replay_modal_shows_external_cutoff(tmp_path):
    from pvz_game import Game
    from pvz_game.replay import Recorder

    game = Game()
    game.reset()
    recorder = Recorder(
        game,
        metadata={
            "outcome": "truncated",
            "termination_reason": "time_limit",
            "policy_id": "shared",
        },
    )
    recorder.step(ticks=1)
    path = tmp_path / "partial.json"
    recorder.save(path)
    app = App(replay_path=path)
    try:
        assert app.mode == Screen.PLAYING
        app.advance()
        assert app.mode == Screen.ENDED
        text = []
        original = app.text

        def capture(value, *args, **kwargs):
            text.append(str(value))
            return original(value, *args, **kwargs)

        app.text = capture
        app.draw()
        assert "Replay truncated" in text
        assert "time limit" in text
        assert app.game.observe().status.value == "running"
        app.restart()
        assert app.playback.display_outcome == "running"
    finally:
        pygame.quit()
