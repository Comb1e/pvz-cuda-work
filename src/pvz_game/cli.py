"""Command line entry points; UI imports are deliberately lazy."""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from time import perf_counter

from . import Game, Rules, Status, load_scenario


def benchmark(level: str, seed: int, ticks: int) -> dict:
    game = Game()
    game.reset(level, seed)
    completed = 0
    started = perf_counter()
    while completed < ticks:
        if game.observe().status != Status.RUNNING:
            game.reset(level, seed)
        game.step()  # Includes events and a full detached public observation every tick.
        completed += 1
    seconds = perf_counter() - started
    return {
        "level": level,
        "seed": seed,
        "ticks": completed,
        "seconds": round(seconds, 4),
        "ticks_per_second": round(completed / seconds, 1),
        "realtime_multiple": round(completed / seconds / 20, 1),
        "workload": "wait-only full API; reset on completion; observation each tick",
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pvz", description="Lawn Lab — daytime defense")
    commands = parser.add_subparsers(dest="command", required=True)
    play = commands.add_parser("play", help="open the interactive game")
    play.add_argument("--level", choices=("easy", "standard", "hard"))
    play.add_argument("--seed", type=int, help="defaults to the seed in UI settings (42)")
    play.add_argument("--rules", type=Path)
    play.add_argument("--scenario", type=Path, help="explicit LevelSpec TOML")
    play.add_argument("--ui-config", type=Path)
    play.add_argument("--record", type=Path, help="save a replay when leaving the game")
    replay = commands.add_parser("replay", help="verify or watch a recorded game")
    replay.add_argument("path", type=Path)
    display = replay.add_mutually_exclusive_group()
    display.add_argument("--watch", action="store_true")
    display.add_argument(
        "--frame", type=Path, help="save the verified final frame without a window"
    )
    bench = commands.add_parser("benchmark", help="measure headless simulation and state export")
    bench.add_argument("--level", choices=("easy", "standard", "hard"), default="standard")
    bench.add_argument("--seed", type=int, default=42)
    bench.add_argument("--ticks", type=int, default=20000)
    bench.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "play":
            from .ui import App

            if args.scenario and args.level:
                parser.error("choose --level or --scenario")
            level = load_scenario(args.scenario) if args.scenario else args.level
            rules = Rules.from_toml(args.rules) if args.rules else Rules()
            App(
                level=level,
                seed=args.seed,
                rules=rules,
                record_path=args.record,
                ui_config=args.ui_config,
            ).run()
        elif args.command == "replay":
            from .replay import Playback

            if args.watch:
                from .ui import App

                App(replay_path=args.path).run()
            else:
                playback = Playback(args.path)
                game = playback.verify()
                obs = game.observe()
                summary = {
                    "verified": True,
                    "status": obs.status.value,
                    "tick": obs.tick,
                    "hash": game.state_hash(),
                }
                if playback.metadata:
                    summary.update(metadata=playback.metadata, outcome=playback.display_outcome)
                if args.frame:
                    from .rendering import BoardRenderer, RenderContext, pygame

                    frame = BoardRenderer().render(
                        obs,
                        context=RenderContext(
                            policy_id=playback.metadata.get("policy_id"),
                            outcome=playback.display_outcome,
                            termination_reason=playback.metadata.get("termination_reason"),
                        ),
                    )
                    args.frame.parent.mkdir(parents=True, exist_ok=True)
                    pygame.image.save(frame, args.frame)
                    summary["frame"] = str(args.frame)
                print(json.dumps(summary, indent=2))
        else:
            if args.ticks <= 0:
                parser.error("--ticks must be positive")
            result = benchmark(args.level, args.seed, args.ticks)
            text = json.dumps(result, indent=2)
            print(text)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text + "\n", "utf-8")
    except ModuleNotFoundError as exc:
        if exc.name == "pygame":
            parser.exit(2, 'Install the UI with: python -m pip install ".[ui]"\n')
        raise
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"pvz: {exc}\n")
    return 0
