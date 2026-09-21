"""Read per-tick research demos without installing a learning framework.

The format permits immediate planting/digging between ordinary combat ticks.
The Game API and its version-1 replay timing remain unchanged.
"""

from dataclasses import replace

from .config import Rules, integer
from .engine import Game
from .replay import Playback, RecordedOperation, decode_action, read_recording
from .types import Dig, Place, Wait

ACTION_PHASE_REPLAY_VERSION = "pvz-rl/actions-v1"


class ActionPhaseGame(Game):
    def step(self, action=Wait(), *, ticks=1):
        if type(ticks) is not int or ticks != 0:
            return super().step(action, ticks=ticks)
        if not isinstance(action, (Place, Dig)):
            raise ValueError("Zero-tick calls require a planting or digging action")
        self._applying_action = True
        try:
            return super().step(action, ticks=1)
        finally:
            self._applying_action = False

    def _advance(self):
        if not getattr(self, "_applying_action", False):
            super()._advance()


class ActionPhasePlayback(Playback):
    """Reuse native seeking and hash checks, applying operations between ticks.

    A displayed tick includes all instantaneous operations recorded at that tick.
    This also defines seeking to tick zero and recordings ending mid-action-phase.
    Playback.step still advances exactly one simulation tick for native UI/video.
    """

    def __init__(self, source):
        data = read_recording(source)
        if data.get("replay_version") != ACTION_PHASE_REPLAY_VERSION:
            raise ValueError("Incompatible research action-phase replay")
        game = ActionPhaseGame(Rules(data["initial"]["rules"]))
        game.restore(data["initial"])
        end = game.observe().tick
        for entry in data["entries"]:
            integer(entry["tick"], "replay tick")
            integer(entry["ticks"], "replay ticks")
            if entry["tick"] != end:
                raise ValueError("replay tick mismatch")
            action = decode_action(entry["action"])
            game.validate_action(action)
            if entry["ticks"] == 0 and not isinstance(action, (Place, Dig)):
                raise ValueError("Zero-tick replay entries must plant or dig")
            end += entry["ticks"]
        # Native setup validates the positive-time timeline, metadata, and cache.
        # Instant operations are validated above and executed by our pinned adapter.
        skeleton = {
            **data,
            "replay_version": 1,
            "entries": [e for e in data["entries"] if e["ticks"]],
        }
        if not skeleton["entries"]:
            skeleton.update(final_hash=game.state_hash(), final_status=game.observe().status.value)
        super().__init__(skeleton)
        self.game, self.data, self.done = game, data, False
        self._drain_instant()
        self._initial_cursor = self._checkpoint()

    def _drain_instant(self):
        events = []
        while self.index < len(self.data["entries"]):
            entry = self.data["entries"][self.index]
            if entry["ticks"]:
                break
            if entry["tick"] != self.current_tick:
                raise ValueError("replay tick mismatch")
            action = decode_action(entry["action"])
            result = self.game.step(action, ticks=0)
            self.last_operation = RecordedOperation(entry["tick"], action, result.action_result)
            events.extend(result.events)
            if "state_hash" in entry and entry["state_hash"] != self.game.state_hash():
                raise ValueError(f"replay state mismatch at entry {self.index}")
            self.index += 1
        if self.index == len(self.data["entries"]):
            self._finish()
        return events

    def step(self):
        result = super().step()
        events = self._drain_instant()
        if self.current_tick in self._cache:
            self._cache[self.current_tick] = self._checkpoint()
        return replace(result, observation=self.game.observe(), events=(*result.events, *events))
