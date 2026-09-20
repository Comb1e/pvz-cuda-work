"""Render replay transport and live-recording screens for visual inspection."""

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from pvz_game import Game, Place
from pvz_game.demo_ui import LivePreview
from pvz_game.ui import App, Screen


def main():
    output = Path("artifacts/demo-previews")
    output.mkdir(parents=True, exist_ok=True)
    app = App(replay_path=Path("tests/fixtures/hard-seed42.json"), speed=8)
    app.request_seek(4300)
    app.update(0)
    app.draw()
    pygame.image.save(app.surface, output / "seeking.png")
    while app.mode == Screen.SEEKING:
        app.update(0)
    app.draw()
    pygame.image.save(app.surface, output / "playback.png")
    app.request_seek(app.playback.end_tick)
    while app.mode == Screen.SEEKING:
        app.update(0)
    app.draw()
    pygame.image.save(app.surface, output / "completed.png")
    pygame.quit()
    game = Game()
    game.reset()
    preview = LivePreview(game.observe(), speed=2)
    action = Place("sunflower", 2, 0)
    preview.after_tick(game.step(action), action)
    preview.draw()
    pygame.image.save(preview.surface, output / "live.png")
    preview.close()
    pygame.quit()
    print(output.resolve())


if __name__ == "__main__":
    main()
