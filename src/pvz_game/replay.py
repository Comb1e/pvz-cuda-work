"""Portable action recordings with exact state verification."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path

from .config import Rules, integer
from .engine import Game
from .types import Action, Dig, Place, Status, StepResult, Wait

REPLAY_VERSION = 1


def _metadata_copy(metadata: dict | None) -> dict:
    """Validate JSON annotations without adding them to any simulation object."""
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValueError("replay metadata must be a JSON object")

    def check_keys(value):
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError("metadata object keys must be strings")
            for item in value.values():
                check_keys(item)
        elif isinstance(value, list):
            for item in value:
                check_keys(item)
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("metadata values must be JSON values")

    try:
        encoded = json.dumps(metadata, allow_nan=False)
        check_keys(metadata)
        result = json.loads(encoded)
    except (TypeError, RecursionError) as exc:
        raise ValueError("metadata must contain finite, acyclic JSON values") from exc
    for key in ("outcome", "termination_reason", "policy_id", "checkpoint_sha256"):
        if key in result and not isinstance(result[key], str):
            raise ValueError(f"metadata {key} must be a string")
    if "outcome" in result and result["outcome"] not in (
        "running",
        "won",
        "lost",
        "truncated",
        "interrupted",
    ):
        raise ValueError("unknown metadata outcome")
    return result


def presentation_outcome(status: Status, external_outcome: str | None = None) -> str:
    """External cutoffs can label a running state; they cannot replace a game outcome."""
    if status == Status.RUNNING and external_outcome in ("truncated", "interrupted"):
        return external_outcome
    return status.value


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

    def __init__(self, game: Game, hash_interval: int = 100, *, metadata: dict | None = None):
        integer(hash_interval, "hash_interval", 1)
        self._metadata = _metadata_copy(metadata)
        self.game = game
        self.hash_interval = hash_interval
        self.initial = game.snapshot()
        self.entries: list[dict] = []

    @property
    def metadata(self) -> dict:
        return copy.deepcopy(self._metadata)

    def update_metadata(self, metadata: dict):
        """Merge detached annotations, for example when an external time limit fires."""
        update = _metadata_copy(metadata)
        self._metadata = _metadata_copy({**self._metadata, **update})

    def step(self, action: Action = Wait(), *, ticks: int = 1) -> StepResult:
        tick = self.game.observe().tick
        result = self.game.step(action, ticks=ticks)
        entry = {"tick": tick, "action": action_dict(action), "ticks": result.ticks_advanced}
        if (len(self.entries) + 1) % self.hash_interval == 0:
            entry["state_hash"] = self.game.state_hash()
        self.entries.append(entry)
        return result

    def to_dict(self) -> dict:
        data = {
            "replay_version": REPLAY_VERSION,
            "initial": copy.deepcopy(self.initial),
            "entries": copy.deepcopy(self.entries),
            "final_hash": self.game.state_hash(),
            "final_status": self.game.observe().status.value,
        }
        if self._metadata:
            data["metadata"] = self.metadata
        return data

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
        self._metadata = _metadata_copy(data.get("metadata"))
        self.game = Game(Rules(data["initial"]["rules"]))
        self.game.restore(data["initial"])
        self.data = data
        self.index = 0
        self.offset = 0
        self.done = False
        if not data["entries"]:
            self._finish()

    @property
    def metadata(self) -> dict:
        return copy.deepcopy(self._metadata)

    @property
    def display_outcome(self) -> str:
        external = self._metadata.get("outcome") if self.done else None
        return presentation_outcome(self.game.observe().status, external)

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

    def verify(self) -> Game:
        """Advance to the recorded end, retaining metadata and the verified display outcome."""
        while not self.done:
            self.step()
        return self.game


def verify_replay(path: dict | str | Path) -> Game:
    return Playback(path).verify()
