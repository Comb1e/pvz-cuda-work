"""Compact operation demos. No model loading, display dependency, or game-rule changes."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .config import LevelSpec, Rules, WaveSpec, bundled, integer, load_scenario
from .engine import Game
from .replay import Playback, Recorder, decode_action, presentation_outcome, validate_speed
from .types import Action, Observation, Status, StepResult, Wait


class DemoCancelled(RuntimeError):
    """The live window closed. Completed ticks have been saved by the session."""


@dataclass(frozen=True, slots=True)
class ScheduledAction:
    tick: int
    action: Action


@dataclass(frozen=True, slots=True)
class DemoResult:
    path: Path
    observation: Observation
    outcome: str
    ticks_recorded: int
    duration_seconds: float
    final_hash: str


class DemoSession:
    """Route every game step through this session while recording; finish saves once.

    Live mode synchronously pumps its window while step is executing. The caller owns
    the time between calls. Use the context manager to preserve completed calls on errors.
    """

    def __init__(
        self,
        game: Game,
        *,
        output: str | Path,
        live: bool = False,
        speed: float = 1,
        metadata: dict | None = None,
        overwrite: bool = False,
    ):
        if not isinstance(game, Game):
            raise TypeError("game must be a reset Game")
        if type(live) is not bool or type(overwrite) is not bool:
            raise TypeError("live and overwrite must be booleans")
        validate_speed(speed)
        self.output = Path(output)
        if self.output.exists() and (not overwrite or self.output.is_dir()):
            raise FileExistsError(self.output)
        self.game = game
        self.recorder = Recorder(
            game, bundled("demo.toml")["hash_interval_steps"], metadata=metadata
        )
        self.overwrite = overwrite
        self.start_tick = game.observe().tick
        self.result: DemoResult | None = None
        self._preview = None
        if live:
            from .demo_ui import LivePreview

            self._preview = LivePreview(
                game.observe(), speed=speed, metadata=self.recorder.metadata
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.result is None:
            self.finish(termination_reason="caller_error" if exc_type else None)
        return False

    def step(self, action: Action = Wait(), *, ticks: int = 1) -> StepResult:
        if self.result is not None:
            raise RuntimeError("demo session is finished")
        try:
            return self.recorder._step(
                action,
                ticks=ticks,
                before_tick=self._preview.before_tick if self._preview else None,
                after_tick=self._preview.after_tick if self._preview else None,
            )
        except DemoCancelled:
            self.finish(outcome="interrupted", termination_reason="window_closed")
            raise

    def finish(
        self, *, outcome: str | None = None, termination_reason: str | None = None
    ) -> DemoResult:
        if self.result is not None:
            return self.result
        if outcome not in (None, "truncated", "interrupted"):
            raise ValueError("external outcome must be truncated or interrupted")
        if termination_reason is not None and not isinstance(termination_reason, str):
            raise TypeError("termination_reason must be a string")
        obs = self.game.observe()
        actual_outcome = presentation_outcome(obs.status, outcome or "interrupted")
        metadata = {"outcome": actual_outcome}
        if obs.status == Status.RUNNING:
            metadata["termination_reason"] = termination_reason or "recording_stopped"
        self.recorder.update_metadata(metadata)
        try:
            # Detect bypassed session steps before publishing an unusable artifact.
            Playback(self.recorder.to_dict()).verify()
            self.recorder.save(self.output, overwrite=self.overwrite)
            duration = obs.tick - self.start_tick
            self.result = DemoResult(
                self.output,
                obs,
                actual_outcome,
                duration,
                duration / obs.tick_rate,
                self.game.state_hash(),
            )
            return self.result
        finally:
            if self._preview:
                self._preview.close()


def generate_demo(
    *,
    output: str | Path,
    actions: Sequence[ScheduledAction] = (),
    level: str | LevelSpec | WaveSpec = "standard",
    seed: int = 42,
    rules: Rules | None = None,
    max_ticks: int | None = None,
    live: bool = False,
    speed: float = 1,
    metadata: dict | None = None,
    overwrite: bool = False,
) -> DemoResult:
    """Fill gaps with waits; continue to a natural outcome or an explicit tick cutoff."""
    if max_ticks is not None:
        integer(max_ticks, "max_ticks")
    game = Game(rules)
    game.reset(level, seed)
    scheduled = tuple(actions)
    previous = -1
    for entry in scheduled:
        if not isinstance(entry, ScheduledAction):
            raise TypeError("actions must contain ScheduledAction values")
        integer(entry.tick, "action tick")
        if entry.tick <= previous:
            raise ValueError("action ticks must be strictly increasing")
        game.validate_action(
            entry.action
        )  # Malformed actions fail before opening any output/window.
        previous = entry.tick
    batch = bundled("demo.toml")["generation_batch_ticks"]
    with DemoSession(
        game, output=output, live=live, speed=speed, metadata=metadata, overwrite=overwrite
    ) as session:
        index = 0
        try:
            while game.observe().status == Status.RUNNING:
                tick = game.observe().tick
                if max_ticks is not None and tick >= max_ticks:
                    return session.finish(outcome="truncated", termination_reason="max_ticks")
                action = Wait()
                if index < len(scheduled) and scheduled[index].tick == tick:
                    action = scheduled[index].action
                    index += 1
                boundary = tick + batch
                if index < len(scheduled):
                    boundary = min(boundary, scheduled[index].tick)
                if max_ticks is not None:
                    boundary = min(boundary, max_ticks)
                session.step(action, ticks=boundary - tick)
        except DemoCancelled:
            return session.result
        return session.finish()


def load_demo_script(path: str | Path) -> dict:
    """Read [demo], [metadata], and [[actions]] tables into generate_demo keyword arguments."""
    path = Path(path)
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    if set(data) - {"demo", "metadata", "actions"}:
        raise ValueError("unknown demo script section")
    options = data.get("demo", {})
    if not isinstance(options, dict) or set(options) - {
        "level",
        "scenario",
        "rules",
        "seed",
        "max_ticks",
    }:
        raise ValueError("unknown demo setting")
    options = dict(options)
    if "level" in options and "scenario" in options:
        raise ValueError("choose level or scenario")
    if "scenario" in options:
        options["level"] = load_scenario(path.parent / options.pop("scenario"))
    if "rules" in options:
        options["rules"] = Rules.from_toml(path.parent / options["rules"])
    actions = []
    try:
        for entry in data.get("actions", []):
            entry = dict(entry)
            tick = entry.pop("tick")
            actions.append(ScheduledAction(tick, decode_action(entry)))
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid demo action table") from exc
    return {**options, "actions": tuple(actions), "metadata": data.get("metadata")}
