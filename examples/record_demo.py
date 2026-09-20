"""Supply operations from an existing loop, optionally previewing them live."""

import argparse
from pathlib import Path

from pvz_game import Game, Place, Wait
from pvz_game.demo import DemoCancelled, DemoSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("demos/recorded.pvzdemo"))
    args = parser.parse_args()
    game = Game()
    game.reset("standard", seed=42)
    with DemoSession(
        game,
        output=args.output,
        live=args.live,
        metadata={"title": "Operations from an external loop"},
    ) as demo:
        try:
            for action, ticks in [
                (Place("sunflower", 2, 0), 200),
                (Place("sunflower", 1, 0), 200),
                (Wait(), 200),
            ]:
                result = demo.step(action, ticks=ticks)
                print(result.observation.tick, result.action_result)
            summary = demo.finish(outcome="truncated", termination_reason="sample_end")
        except DemoCancelled:
            summary = demo.result
    print(summary.path, summary.outcome, summary.final_hash)


if __name__ == "__main__":
    main()
