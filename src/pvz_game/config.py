"""Validated, detached configuration. All timing is converted to exact ticks."""

from __future__ import annotations

import copy
import hashlib
import json
import random
import tomllib
from dataclasses import asdict, dataclass
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType

PLANT_TYPES = (
    "sunflower",
    "peashooter",
    "wall_nut",
    "cherry_bomb",
    "potato_mine",
    "snow_pea",
    "chomper",
    "repeater",
)
ZOMBIE_TYPES = ("basic", "flag", "conehead", "buckethead", "pole_vaulting")


def bundled(name: str) -> dict:
    return tomllib.loads(files("pvz_game").joinpath("data", name).read_text("utf-8"))


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def scaled(value: object, scale: int, name: str, minimum: int = 0) -> int:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a number")
    n = Decimal(str(value)) * scale
    if not n.is_finite() or n != n.to_integral_value() or n < minimum:
        raise ValueError(f"{name} must be >= {minimum / scale} and align to 1/{scale}")
    return int(n)


class Rules:
    """Read-only rules loaded from TOML or a detached dictionary."""

    def __init__(self, data: dict | None = None):
        raw = copy.deepcopy(bundled("rules.toml") if data is None else data)
        expected = bundled("rules.toml")
        if set(raw) != set(expected) or not isinstance(raw["version"], str):
            raise ValueError("rules require version, game, plants and zombies")
        if set(raw["game"]) != set(expected["game"]):
            raise ValueError("unknown or missing game rule")
        if set(raw["plants"]) != set(PLANT_TYPES):
            raise ValueError("rules must define all eight known plants")
        if set(raw["zombies"]) != set(ZOMBIE_TYPES):
            raise ValueError("rules must define all five known zombies")
        g = raw["game"]
        for name in ("tick_rate", "rows", "cols", "units_per_tile"):
            integer(g[name], name, 1)
        if (g["tick_rate"], g["rows"], g["cols"]) != (100, 5, 9):
            raise ValueError("version 1.1 supports a 5x9 board at 100 Hz")
        if g["units_per_tile"] % 2:
            raise ValueError("units_per_tile must be even")
        rate, units = g["tick_rate"], g["units_per_tile"]
        velocity_scale = bundled("mechanics.toml")["source_velocity_scale"]
        game = {}
        for key, value in g.items():
            if key.endswith("_seconds"):
                game[key.replace("_seconds", "_ticks")] = scaled(value, rate, key, 1)
            elif key.endswith("_x"):
                game[key] = scaled(value, units, key, -units)
            elif key.endswith("_speed") or key.endswith("_offset") or key == "vault_distance":
                game[key] = scaled(value, units, key, 1)
            else:
                game[key] = integer(value, key)
        if not g["house_x"] < g["mower_trigger_x"] < g["spawn_x"]:
            raise ValueError("house, mower and spawn boundaries must be ordered")
        if game["initial_sun"] > game["sun_cap"]:
            raise ValueError("initial_sun exceeds cap")
        if not 0 < game["contact_offset"] < units // 2:
            raise ValueError("contact_offset must be between zero and half a tile")
        if not 0 < game["projectile_offset"] <= game["contact_offset"]:
            raise ValueError("projectile_offset must not exceed contact_offset")
        for key in ("slow_denominator", "headless_decay_chance", "mower_hit_ticks"):
            integer(game[key], key, 1)
        if not 0 < game["slow_numerator"] <= game["slow_denominator"]:
            raise ValueError("invalid chilled movement fraction")
        if game["sky_first_min_ticks"] > game["sky_first_max_ticks"]:
            raise ValueError("invalid initial sky range")
        groups = {}
        for group in ("plants", "zombies"):
            parsed = {}
            for kind, definition in raw[group].items():
                if set(definition) != set(expected[group][kind]):
                    raise ValueError(f"unknown or missing fields in {kind}")
                fields = {}
                for key, value in definition.items():
                    if key.endswith("_seconds"):
                        fields[key.replace("_seconds", "_ticks")] = scaled(value, rate, key, 1)
                    elif key.endswith("speed"):
                        # Zombie velocities live in source-space thousandths.
                        # Gait integration converts them to the board's fixed
                        # point units, so changing units_per_tile cannot change
                        # a zombie's physical speed.
                        fields[key] = scaled(
                            value, velocity_scale if group == "zombies" else units, key
                        )
                    else:
                        fields[key] = integer(value, key, 1 if key == "health" else 0)
                parsed[kind] = MappingProxyType(fields)
                if group == "zombies" and (
                    fields["speed"] > fields["max_speed"]
                    or fields.get("pole_speed", 0) > fields.get("pole_max_speed", 0)
                ):
                    raise ValueError("invalid zombie speed range")
            groups[group] = MappingProxyType(parsed)
        self._raw = raw
        self.version = raw["version"]
        self.game = MappingProxyType(game)
        self.plants = groups["plants"]
        self.zombies = groups["zombies"]
        self.digest = canonical_hash(raw)

    @classmethod
    def from_toml(cls, path: str | Path) -> Rules:
        with open(path, "rb") as stream:
            return cls(tomllib.load(stream))

    def to_dict(self) -> dict:
        return copy.deepcopy(self._raw)


@dataclass(frozen=True, slots=True)
class Spawn:
    tick: int
    zombie_type: str
    row: int
    wave: int = 1
    x: int | None = None  # Fixed-point units; omitted means the configured spawn boundary.


@dataclass(frozen=True, slots=True)
class InitialPlant:
    plant_type: str
    row: int
    col: int


@dataclass(frozen=True, slots=True)
class LevelSpec:
    name: str
    spawns: tuple[Spawn, ...] = ()
    initial_sun: int | None = None
    plants: tuple[InitialPlant, ...] = ()
    mowers: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> LevelSpec:
        if set(data) - {"name", "spawns", "initial_sun", "plants", "mowers"}:
            raise ValueError("unknown explicit scenario field")
        return cls(
            name=data["name"],
            spawns=tuple(Spawn(**s) for s in data["spawns"]),
            initial_sun=data.get("initial_sun"),
            plants=tuple(InitialPlant(**p) for p in data.get("plants", [])),
            mowers=data.get("mowers", True),
        )

    @classmethod
    def from_toml(cls, path: str | Path) -> LevelSpec:
        with open(path, "rb") as stream:
            return cls.from_dict(tomllib.load(stream))


@dataclass(frozen=True, slots=True)
class WaveSpec:
    """Configurable generated level; lanes and spawn jitter are drawn only at reset."""

    name: str
    waves: tuple[tuple[str, ...], ...]
    preparation_seconds: float = 30
    wave_seconds: float = 25
    jitter_seconds: float = 5
    initial_sun: int | None = None
    plants: tuple[InitialPlant, ...] = ()
    mowers: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> WaveSpec:
        values = dict(data)
        values["waves"] = tuple(tuple(wave) for wave in values["waves"])
        values["plants"] = tuple(InitialPlant(**p) for p in values.get("plants", []))
        try:
            return cls(**values)
        except TypeError as exc:
            raise ValueError(f"invalid generated scenario: {exc}") from exc

    @classmethod
    def from_toml(cls, path: str | Path) -> WaveSpec:
        with open(path, "rb") as stream:
            return cls.from_dict(tomllib.load(stream))


def load_scenario(path: str | Path) -> LevelSpec | WaveSpec:
    with open(path, "rb") as stream:
        data = tomllib.load(stream)
    return WaveSpec.from_dict(data) if "waves" in data else LevelSpec.from_dict(data)


def validate_level(level: LevelSpec, rules: Rules) -> LevelSpec:
    if not isinstance(level.name, str) or not level.name:
        raise ValueError("level name must be nonempty")
    g = rules.game
    if level.initial_sun is not None:
        integer(level.initial_sun, "initial_sun")
        if level.initial_sun > g["sun_cap"]:
            raise ValueError("initial_sun exceeds cap")
    if type(level.mowers) is not bool:
        raise ValueError("mowers must be boolean")
    for s in level.spawns:
        integer(s.tick, "spawn tick", 1)
        integer(s.wave, "wave", 1)
        integer(s.row, "row")
        if s.row >= g["rows"] or s.zombie_type not in rules.zombies:
            raise ValueError("invalid spawn row or zombie type")
        if s.x is not None:
            integer(s.x, "spawn x")
            if s.x > g["spawn_x"]:
                raise ValueError("spawn x lies beyond the spawn boundary")
    occupied = set()
    for p in level.plants:
        integer(p.row, "row")
        integer(p.col, "col")
        if p.row >= g["rows"] or p.col >= g["cols"] or p.plant_type not in rules.plants:
            raise ValueError("invalid initial plant")
        if (p.row, p.col) in occupied:
            raise ValueError("duplicate initial plant tile")
        occupied.add((p.row, p.col))
    return LevelSpec(
        level.name,
        tuple(sorted(level.spawns, key=lambda s: s.tick)),
        level.initial_sun,
        tuple(level.plants),
        level.mowers,
    )


def resolve_level(level: str | LevelSpec | WaveSpec, rules: Rules, rng: random.Random) -> LevelSpec:
    if isinstance(level, LevelSpec):
        return validate_level(level, rules)
    if isinstance(level, str):
        presets = bundled("levels.toml")
        if level not in presets:
            raise ValueError(f"unknown level {level!r}; choose {', '.join(presets)}")
        level = WaveSpec.from_dict({"name": level, **presets[level]})
    if not isinstance(level, WaveSpec):
        raise TypeError("level must be a preset name, LevelSpec, or WaveSpec")
    rate = rules.game["tick_rate"]
    preparation = scaled(level.preparation_seconds, rate, "preparation", 1)
    spacing = scaled(level.wave_seconds, rate, "wave spacing", 1)
    jitter = scaled(level.jitter_seconds, rate, "jitter")
    if not level.waves or any(not wave for wave in level.waves):
        raise ValueError("generated scenarios require nonempty waves")
    if jitter >= spacing:
        raise ValueError("wave jitter must be shorter than wave spacing")
    spawns = tuple(
        Spawn(
            preparation + wave * spacing + rng.randint(0, jitter),
            kind,
            rng.randrange(rules.game["rows"]),
            wave + 1,
        )
        for wave, kinds in enumerate(level.waves)
        for kind in kinds
    )
    return validate_level(
        LevelSpec(level.name, spawns, level.initial_sun, level.plants, level.mowers), rules
    )
