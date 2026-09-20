"""Attach wrapper metadata and export a final frame without initializing a display."""

from pathlib import Path

from pvz_game import Game, Place
from pvz_game.rendering import BoardRenderer, RenderContext
from pvz_game.replay import Playback, Recorder

game = Game()
game.reset("standard", seed=42)
recorder = Recorder(
    game,
    metadata={
        "policy_id": "example-controller",
        "experiment": {"description": "Short integration example, no trained checkpoint"},
    },
)
recorder.step(Place("sunflower", 2, 0), ticks=200)
recorder.update_metadata({"outcome": "truncated", "termination_reason": "time_limit"})
destination = Path("artifacts/offscreen-example.json")
recorder.save(destination)

playback = Playback(destination)
playback.verify()
renderer = BoardRenderer(size=(1000, 600))
frame = renderer.rgb_frame(
    playback.game.observe(),
    context=RenderContext(
        policy_id=playback.metadata["policy_id"],
        outcome=playback.display_outcome,
        termination_reason=playback.metadata["termination_reason"],
    ),
)
# This PPM writer uses only packed RGB bytes. FFmpeg accepts the same bytes as rgb24.
destination.with_suffix(".ppm").write_bytes(
    f"P6\n{frame.width} {frame.height}\n255\n".encode("ascii") + frame.data
)
print("Engine:", playback.game.observe().status.value, "Display:", playback.display_outcome)
print(destination.with_suffix(".ppm").resolve())
