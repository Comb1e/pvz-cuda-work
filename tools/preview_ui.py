"""Render a menu and an illustrative live scenario for visual QA."""

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from pvz_game import InitialPlant, LevelSpec, Spawn
from pvz_game.ui import App

out = Path("artifacts")
out.mkdir(exist_ok=True)
app = App()
app.draw()
pygame.image.save(app.surface, out / "menu.png")
plants = tuple(InitialPlant("sunflower", row, 0) for row in range(5)) + (
    InitialPlant("peashooter", 0, 2),
    InitialPlant("snow_pea", 1, 2),
    InitialPlant("repeater", 2, 2),
    InitialPlant("chomper", 3, 3),
    InitialPlant("potato_mine", 4, 3),
    InitialPlant("wall_nut", 0, 5),
    InitialPlant("wall_nut", 2, 5),
    InitialPlant("cherry_bomb", 4, 5),
)
spawns = tuple(
    Spawn(1, kind, row, x=8000)
    for row, kind in enumerate(("basic", "conehead", "buckethead", "flag", "pole_vaulting"))
) + (Spawn(6000, "basic", 4),)
app.start(LevelSpec("showcase", spawns, 350, plants))
app.advance()
app.selected = "peashooter"
app.draw()
pygame.image.save(app.surface, out / "gameplay.png")
app.toggle_pause()
app.draw()
pygame.image.save(app.surface, out / "paused.png")
pygame.quit()
print(out.resolve())
