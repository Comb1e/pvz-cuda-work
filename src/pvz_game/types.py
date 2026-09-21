"""Public value types. Observations contain no references to mutable engine state."""

from dataclasses import dataclass
from enum import StrEnum

API_VERSION = 1
SNAPSHOT_VERSION = 1
# Simulation compatibility identifier, included in state hashes. Presentation-only
# package releases retain it so existing snapshots and research baselines still replay.
ENGINE_VERSION = "1.0.0"
PACKAGE_VERSION = "1.3.0"


class Status(StrEnum):
    RUNNING = "running"
    WON = "won"
    LOST = "lost"


@dataclass(frozen=True, slots=True)
class Wait:
    pass


@dataclass(frozen=True, slots=True)
class Place:
    plant_type: str
    row: int
    col: int


@dataclass(frozen=True, slots=True)
class Dig:
    row: int
    col: int


Action = Wait | Place | Dig


@dataclass(frozen=True, slots=True)
class ActionResult:
    accepted: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Event:
    kind: str
    tick: int
    entity_id: int | None = None
    details: tuple[tuple[str, int | str], ...] = ()

    def get(self, key: str, default=None):
        return dict(self.details).get(key, default)


@dataclass(frozen=True, slots=True)
class CardView:
    plant_type: str
    cost: int
    cooldown_ticks: int
    recharge_ticks: int


@dataclass(frozen=True, slots=True)
class PlantView:
    id: int
    plant_type: str
    row: int
    col: int
    health: int
    max_health: int
    state: str
    timer_ticks: int


@dataclass(frozen=True, slots=True)
class ZombieView:
    id: int
    zombie_type: str
    row: int
    x: int
    health: int
    armor: int
    state: str
    slow_ticks: int
    has_pole: bool
    timer_ticks: int


@dataclass(frozen=True, slots=True)
class ProjectileView:
    id: int
    row: int
    x: int
    damage: int
    icy: bool


@dataclass(frozen=True, slots=True)
class MowerView:
    row: int
    x: int
    state: str


@dataclass(frozen=True, slots=True)
class ZombieCounts:
    initial_total: int
    spawned: int
    alive: int
    defeated: int
    not_yet_spawned: int
    remaining: int


@dataclass(frozen=True, slots=True)
class Observation:
    api_version: int
    tick: int
    elapsed_seconds: float
    tick_rate: int
    units_per_tile: int
    rows: int
    cols: int
    level: str
    status: Status
    sun: int
    cards: tuple[CardView, ...]
    plants: tuple[PlantView, ...]
    zombies: tuple[ZombieView, ...]
    projectiles: tuple[ProjectileView, ...]
    mowers: tuple[MowerView, ...]
    wave: int
    total_waves: int
    counts: ZombieCounts


@dataclass(frozen=True, slots=True)
class StepResult:
    observation: Observation
    action_result: ActionResult
    events: tuple[Event, ...]
    status: Status
    ticks_advanced: int


class GameFinishedError(RuntimeError):
    """Reset before advancing a completed game."""
