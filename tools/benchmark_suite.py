"""Measure full API, a populated replay, a crowded scenario, and rendering separately."""

import json
import os
from pathlib import Path
from time import perf_counter

from pvz_game import Game, InitialPlant, LevelSpec, Spawn, Status
from pvz_game.cli import benchmark
from pvz_game.replay import Playback


def main():
    report = {"standard_wait": benchmark("standard", 42, 20000)}
    fixture = Path("tests/fixtures/hard-seed42.json")
    started = perf_counter()
    ticks = 0
    for _ in range(3):
        playback = Playback(fixture)
        while not playback.done:
            playback.step()
            ticks += 1
    elapsed = perf_counter() - started
    report["populated_hard_replay"] = {
        "ticks": ticks,
        "seconds": round(elapsed, 4),
        "ticks_per_second": round(ticks / elapsed, 1),
        "realtime_multiple": round(ticks / elapsed / 20, 1),
        "includes": "state export every tick, action decoding, and periodic replay hash verification",
    }
    plants = tuple(InitialPlant("peashooter", row, col) for row in range(5) for col in range(3))
    spawns = tuple(
        Spawn(1, "buckethead", index % 5, x=8000 + index % 15 * 100) for index in range(200)
    )
    scenario = LevelSpec("stress-200", spawns, 50, plants)
    game = Game()
    game.reset(scenario)
    started = perf_counter()
    for _ in range(4000):
        if game.observe().status != Status.RUNNING:
            game.reset(scenario)
        game.step()
    elapsed = perf_counter() - started
    report["crowded_200_zombies"] = {
        "ticks": 4000,
        "seconds": round(elapsed, 4),
        "ticks_per_second": round(4000 / elapsed, 1),
        "realtime_multiple": round(4000 / elapsed / 20, 1),
    }
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    import pygame

    from pvz_game.ui import App

    app = App(level="hard", seed=42)
    playback = Playback(fixture)
    for _ in range(4000):
        playback.step()
    app.game = playback.game
    before = app.game.state_hash()
    app.draw()
    started = perf_counter()
    for _ in range(120):
        app.draw()
    elapsed = perf_counter() - started
    assert app.game.state_hash() == before
    report["render_only"] = {
        "frames": 120,
        "seconds": round(elapsed, 4),
        "frames_per_second": round(120 / elapsed, 1),
        "display": "SDL dummy surface, excludes real display presentation",
    }
    pygame.quit()
    output = Path("artifacts/benchmarks.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
