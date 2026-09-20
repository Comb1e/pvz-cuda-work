"""Portable action recordings with exact state verification."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path

from .config import Rules, integer
from .engine import Game
from .types import Action, Dig, Place, StepResult, Wait

REPLAY_VERSION = 1


def action_dict(action: Action) -> dict:
    return {"kind": type(action).__name__.lower(), **asdict(action)}


def decode_action(data: dict) -> Action:
    data = dict(data)
    kind = data.pop("kind")
    types = {"wait": Wait, "place": Place, "dig": Dig}
    if kind not in types:
        raise ValueError(f"unknown replay action {kind!r}")
    return types[kind](**data)


class Recorder:
    """Call recorder.step in place of game.step while recording."""

    def __init__(self, game: Game, hash_interval: int = 100):
        integer(hash_interval, "hash_interval", 1)
        self.game = game
        self.hash_interval = hash_interval
        self.initial = game.snapshot()
        self.entries: list[dict] = []

    def step(self, action: Action = Wait(), *, ticks: int = 1) -> StepResult:
        tick = self.game.observe().tick
        result = self.game.step(action, ticks=ticks)
        entry = {"tick": tick, "action": action_dict(action), "ticks": result.ticks_advanced}
        if (len(self.entries) + 1) % self.hash_interval == 0:
            entry["state_hash"] = self.game.state_hash()
        self.entries.append(entry)
        return result

    def to_dict(self) -> dict:
        return {
            "replay_version": REPLAY_VERSION,
            "initial": copy.deepcopy(self.initial),
            "entries": copy.deepcopy(self.entries),
            "final_hash": self.game.state_hash(),
            "final_status": self.game.observe().status.value,
        }

    def save(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), separators=(",", ":")) + "\n", "utf-8", newline="\n"
        )


class Playback:
    """Reproduce a recording one simulation tick at a time, checking each checkpoint."""

    def __init__(self, source: dict | str | Path):
        data = (
            copy.deepcopy(source)
            if isinstance(source, dict)
            else json.loads(Path(source).read_text("utf-8"))
        )
        if data.get("replay_version") != REPLAY_VERSION:
            raise ValueError("incompatible replay version")
        self.game = Game(Rules(data["initial"]["rules"]))
        self.game.restore(data["initial"])
        self.data = data
        self.index = 0
        self.offset = 0
        self.done = False
        if not data["entries"]:
            self._finish()

    def _finish(self):
        if (
            self.game.state_hash() != self.data["final_hash"]
            or self.game.observe().status.value != self.data["final_status"]
        ):
            raise ValueError("replay final state mismatch")
        self.done = True

    def step(self) -> StepResult:
        if self.done:
            raise RuntimeError("replay is complete")
        entry = self.data["entries"][self.index]
        integer(entry["ticks"], "replay ticks", 1)
        if self.game.observe().tick != entry["tick"] + self.offset:
            raise ValueError(f"replay tick mismatch at entry {self.index}")
        action = decode_action(entry["action"]) if self.offset == 0 else Wait()
        result = self.game.step(action)
        self.offset += 1
        if self.offset == entry["ticks"]:
            if "state_hash" in entry and self.game.state_hash() != entry["state_hash"]:
                raise ValueError(f"replay state mismatch at entry {self.index}")
            self.index += 1
            self.offset = 0
            if self.index == len(self.data["entries"]):
                self._finish()
        return result


def verify_replay(path: dict | str | Path) -> Game:
    playback = Playback(path)
    while not playback.done:
        playback.step()
    return playback.game
