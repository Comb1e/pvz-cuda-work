"""Portable action recordings with exact state verification."""

from __future__ import annotations

import copy
import gzip
import json
import os
import tempfile
import zlib
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Rules, bundled, integer
from .engine import Game
from .types import Action, ActionResult, Dig, GameFinishedError, Place, Status, StepResult, Wait

REPLAY_VERSION = 1


def validate_speed(speed):
    speeds = bundled("demo.toml")["speeds"]
    if type(speed) not in (int, float) or speed not in speeds:
        raise ValueError("speed must be one of " + ", ".join(map(str, speeds)))
    return speed


def read_recording(source: dict | str | Path) -> dict:
    if isinstance(source, dict):
        return copy.deepcopy(source)
    try:
        payload = Path(source).read_bytes()
        if payload.startswith(b"\x1f\x8b"):
            payload = gzip.decompress(payload)
        data = json.loads(payload)
    except (EOFError, UnicodeError, json.JSONDecodeError, zlib.error) as exc:
        raise ValueError("invalid or incomplete replay file") from exc
    if not isinstance(data, dict):
        raise ValueError("replay must contain a JSON object")
    return data


def write_recording(data: dict, path: str | Path, *, overwrite: bool = True):
    """Atomically publish JSON or a compressed demo; never expose a partial file."""
    path = Path(path)
    if not overwrite and path.exists():
        raise FileExistsError(path)
    payload = (json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if path.suffix.lower() == ".pvzdemo" or path.name.lower().endswith(".json.gz"):
        payload = gzip.compress(payload, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pvz-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # An atomic exclusive publish also protects against a file created during recording.
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class RecordedOperation:
    tick: int
    action: Action
    result: ActionResult


def operation_text(operation: RecordedOperation | None) -> str:
    if operation is None:
        return "No placement or digging operation yet."
    action = operation.action
    label = f"Place {action.plant_type.replace('_', ' ')}" if isinstance(action, Place) else "Dig"
    verdict = "accepted" if operation.result.accepted else operation.result.reason.replace("_", " ")
    return f"Tick {operation.tick}  /  {label} at ({action.row}, {action.col})  /  {verdict}"


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
        return self._step(action, ticks=ticks)

    def _step(self, action, *, ticks, before_tick=None, after_tick=None):
        """Internal presentation hooks; one record per call, including completed partial calls."""
        integer(ticks, "ticks", 1)
        self.game.validate_action(action)
        if self.game.observe().status != Status.RUNNING:
            raise GameFinishedError("reset before stepping a completed game")
        tick = self.game.observe().tick
        advanced = 0
        try:
            if before_tick is None and after_tick is None:
                result = self.game.step(action, ticks=ticks)
                advanced = result.ticks_advanced
                return result
            events = []
            first = None
            for offset in range(ticks):
                if before_tick:
                    before_tick()
                submitted = action if offset == 0 else Wait()
                result = self.game.step(submitted)
                advanced += result.ticks_advanced
                first = first or result
                events.extend(result.events)
                if after_tick:
                    after_tick(result, submitted)
                if result.status != Status.RUNNING:
                    break
            return StepResult(
                result.observation, first.action_result, tuple(events), result.status, advanced
            )
        finally:
            if advanced:
                self._append(tick, action, advanced)

    def _append(self, tick, action, ticks):
        entry = {"tick": tick, "action": action_dict(action), "ticks": ticks}
        if (len(self.entries) + 1) % self.hash_interval == 0:
            entry["state_hash"] = self.game.state_hash()
        self.entries.append(entry)

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

    def save(self, path: str | Path, *, overwrite: bool = True):
        write_recording(self.to_dict(), path, overwrite=overwrite)


class Playback:
    """Reproduce a recording one simulation tick at a time, checking each checkpoint."""

    def __new__(cls, source):
        # Native readers also accept the explicitly versioned research timeline.
        # Ordinary version-1 recordings keep the original player and semantics.
        if cls is Playback:
            data = read_recording(source)
            if data.get("replay_version") == "pvz-rl/actions-v1":
                from .action_replay import ActionPhasePlayback

                return object.__new__(ActionPhasePlayback)
        return object.__new__(cls)

    def __init__(self, source: dict | str | Path):
        data = read_recording(source)
        if data.get("replay_version") != REPLAY_VERSION:
            raise ValueError("incompatible replay version")
        self._metadata = _metadata_copy(data.get("metadata"))
        self.game = Game(Rules(data["initial"]["rules"]))
        self.game.restore(data["initial"])
        self.data = data
        self.index = 0
        self.offset = 0
        self.done = False
        self.last_operation = None
        settings = bundled("demo.toml")
        self._cache_interval = settings["cache_interval_ticks"]
        self._cache_limit = settings["cache_limit"]
        self._cache = OrderedDict()
        self._start_tick = self.game.observe().tick
        end = self._start_tick
        for entry in data["entries"]:
            integer(entry["tick"], "replay tick")
            integer(entry["ticks"], "replay ticks", 1)
            if entry["tick"] != end:
                raise ValueError("replay tick mismatch")
            self.game.validate_action(decode_action(entry["action"]))
            end += entry["ticks"]
        self._end_tick = end
        if not data["entries"]:
            self._finish()
        self._initial_cursor = self._checkpoint()

    @property
    def start_tick(self) -> int:
        return self._start_tick

    @property
    def end_tick(self) -> int:
        return self._end_tick

    @property
    def current_tick(self) -> int:
        return self.game.observe().tick

    def _checkpoint(self):
        return (self.game.snapshot(), self.index, self.offset, self.done, self.last_operation)

    def seek(self, tick: int):
        """Synchronously seek to an absolute simulation tick; preserve game identity."""
        for _ in self.seek_steps(tick):
            pass
        return self.game.observe()

    def seek_steps(self, tick: int):
        """Yield after each simulated tick so interactive seeking can stay responsive."""
        integer(tick, "seek tick")
        if not self.start_tick <= tick <= self.end_tick:
            raise ValueError("seek tick outside recording")
        return self._seek_steps(tick)

    def _seek_steps(self, tick):
        candidates = [t for t in self._cache if t <= tick]
        closest = max(candidates, default=self.start_tick)
        if not closest <= self.current_tick <= tick:
            saved = self._cache.get(closest, self._initial_cursor)
            snapshot, self.index, self.offset, self.done, self.last_operation = saved
            self.game.restore(snapshot)
        while self.current_tick < tick:
            yield self.step()

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
        if isinstance(action, (Place, Dig)):
            self.last_operation = RecordedOperation(entry["tick"], action, result.action_result)
        self.offset += 1
        if self.offset == entry["ticks"]:
            if "state_hash" in entry and self.game.state_hash() != entry["state_hash"]:
                raise ValueError(f"replay state mismatch at entry {self.index}")
            self.index += 1
            self.offset = 0
            if self.index == len(self.data["entries"]):
                self._finish()
        if (self.current_tick - self.start_tick) % self._cache_interval == 0:
            self._cache[self.current_tick] = self._checkpoint()
            self._cache.move_to_end(self.current_tick)
            while len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)
        return result

    def verify(self) -> Game:
        """Advance to the recorded end, retaining metadata and the verified display outcome."""
        while not self.done:
            self.step()
        return self.game


def verify_replay(path: dict | str | Path) -> Game:
    return Playback(path).verify()
