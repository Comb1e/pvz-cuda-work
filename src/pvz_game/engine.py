"""Fixed-tick simulation. No rendering, wall clock, global RNG, or RL dependency."""

from __future__ import annotations

import copy
import random
from dataclasses import asdict, dataclass

from .config import PLANT_TYPES, LevelSpec, Rules, WaveSpec, canonical_hash, integer, resolve_level
from .randomness import initial_state, next_u32
from .types import (
    API_VERSION,
    ENGINE_VERSION,
    SNAPSHOT_VERSION,
    Action,
    ActionResult,
    CardView,
    Dig,
    Event,
    GameFinishedError,
    MowerView,
    Observation,
    Place,
    PlantView,
    ProjectileView,
    Status,
    StepResult,
    Wait,
    ZombieCounts,
    ZombieView,
)


@dataclass(slots=True)
class _Plant:
    id: int
    kind: str
    row: int
    col: int
    health: int
    state: str
    due: int
    burst_due: int = 0


@dataclass(slots=True)
class _Zombie:
    id: int
    kind: str
    row: int
    x: int
    health: int
    armor: int
    state: str = "walking"
    slow_until: int = 0
    has_pole: bool = False
    vault_until: int = 0
    landing_x: int = 0
    bite_progress: int = 0
    move_remainder: int = 0
    target_id: int = 0
    headless: bool = False
    age: int = 0
    speed: int = 0
    pole_speed: int = 0


@dataclass(slots=True)
class _Projectile:
    id: int
    row: int
    x: int
    damage: int
    icy: bool = False
    move_remainder: int = 0


@dataclass(slots=True)
class _Mower:
    row: int
    x: int
    state: str = "ready"
    move_remainder: int = 0
    chomp_ticks: int = 0


class Game:
    """A single isolated game. Call reset before observe, step, or snapshot."""

    def __init__(self, rules: Rules | None = None):
        self.rules = Rules(None if rules is None else rules.to_dict())
        self._g = self.rules.game
        self._ready = False

    def reset(self, level: str | LevelSpec | WaveSpec = "standard", seed: int = 42) -> Observation:
        integer(seed, "seed")
        rng = random.Random(seed)
        resolved = resolve_level(level, self.rules, rng)  # Validate before replacing a live game.
        self._rng, self._level, self._seed = rng, resolved, seed
        self._tick = 0
        self._status = Status.RUNNING
        self._sun = self._g["initial_sun"] if resolved.initial_sun is None else resolved.initial_sun
        self._gameplay_rng = initial_state(seed)
        self._sky_drops = 0
        self._sky_due = self._random(self._g["sky_first_min_ticks"], self._g["sky_first_max_ticks"])
        self._cooldowns = {
            kind: self.rules.plants[kind].get("initial_recharge_ticks", -1) + 1
            for kind in PLANT_TYPES
        }
        self._plants: dict[int, _Plant] = {}
        self._zombies: dict[int, _Zombie] = {}
        self._projectiles: dict[int, _Projectile] = {}
        self._tiles: dict[tuple[int, int], int] = {}
        self._next_id = 1
        self._spawn_index = 0
        self._defeated = 0
        self._wave = 0
        self._total_waves = max((s.wave for s in resolved.spawns), default=0)
        self._mowers = [
            _Mower(row, self._g["mower_trigger_x"], "ready" if resolved.mowers else "spent")
            for row in range(self._g["rows"])
        ]
        self._events: list[Event] = []
        for p in resolved.plants:
            self._add_plant(p.plant_type, p.row, p.col)
        self._events.clear()
        self._ready = True
        return self.observe()

    def _require_ready(self):
        if not self._ready:
            raise RuntimeError("call reset before using the game")

    def _random(self, minimum: int, maximum: int) -> int:
        self._gameplay_rng = next_u32(self._gameplay_rng)
        return minimum + self._gameplay_rng % (maximum - minimum + 1)

    def _id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def _emit(self, kind: str, entity_id: int | None = None, **details):
        self._events.append(Event(kind, self._tick, entity_id, tuple(sorted(details.items()))))

    def validate_action(self, action: Action) -> ActionResult:
        """The sole legality validator, shared by UI, execution and external callers."""
        self._require_ready()
        if type(action) not in (Wait, Place, Dig):
            raise TypeError("action must be Wait, Place or Dig")
        if isinstance(action, (Place, Dig)):
            if type(action.row) is not int or type(action.col) is not int:
                raise TypeError("row and col must be integers")
            if isinstance(action, Place) and not isinstance(action.plant_type, str):
                raise TypeError("plant_type must be a string")
        if self._status != Status.RUNNING:
            return ActionResult(False, "game_finished")
        if isinstance(action, Wait):
            return ActionResult(True)
        if not (0 <= action.row < self._g["rows"] and 0 <= action.col < self._g["cols"]):
            return ActionResult(False, "outside_board")
        occupied = (action.row, action.col) in self._tiles
        if isinstance(action, Dig):
            return ActionResult(occupied, None if occupied else "empty_tile")
        if action.plant_type not in self.rules.plants:
            return ActionResult(False, "unknown_plant")
        if occupied:
            return ActionResult(False, "occupied_tile")
        if self._cooldowns[action.plant_type] > 0:
            return ActionResult(False, "card_recharging")
        if self._sun < self.rules.plants[action.plant_type]["cost"]:
            return ActionResult(False, "insufficient_sun")
        return ActionResult(True)

    def legal_actions(self) -> tuple[Action, ...]:
        self._require_ready()
        if self._status != Status.RUNNING:
            return ()
        candidates: list[Action] = [Wait()]
        for row in range(self._g["rows"]):
            for col in range(self._g["cols"]):
                if (row, col) in self._tiles:
                    candidates.append(Dig(row, col))
                else:
                    candidates.extend(Place(kind, row, col) for kind in PLANT_TYPES)
        return tuple(a for a in candidates if self.validate_action(a).accepted)

    def step(self, action: Action = Wait(), *, ticks: int = 1) -> StepResult:
        self._require_ready()
        integer(ticks, "ticks", 1)
        accepted = self.validate_action(action)
        if self._status != Status.RUNNING:
            raise GameFinishedError("reset before stepping a completed game")
        self._events = []
        if accepted.accepted:
            if isinstance(action, Place):
                spec = self.rules.plants[action.plant_type]
                self._sun -= spec["cost"]
                self._cooldowns[action.plant_type] = spec["recharge_ticks"] + 1
                self._add_plant(action.plant_type, action.row, action.col)
            elif isinstance(action, Dig):
                self._remove_plant(self._tiles[action.row, action.col], "dug")
        else:
            self._emit("ActionRejected", reason=accepted.reason)
        start = self._tick
        for _ in range(ticks):
            self._advance()
            if self._status != Status.RUNNING:
                break
        return StepResult(
            self.observe(), accepted, tuple(self._events), self._status, self._tick - start
        )

    def _add_plant(self, kind: str, row: int, col: int):
        spec = self.rules.plants[kind]
        state = {"potato_mine": "arming", "cherry_bomb": "fusing"}.get(kind, "ready")
        p = _Plant(
            self._id(),
            kind,
            row,
            col,
            spec["health"],
            state,
            self._tick + spec.get("first_ticks", 0),
        )
        if kind == "sunflower":
            p.due = self._tick + self._random(spec["first_ticks"], spec["first_max_ticks"])
        elif kind in ("peashooter", "snow_pea", "repeater"):
            p.due = self._tick + self._random(0, spec["interval_ticks"])
        self._plants[p.id] = p
        self._tiles[row, col] = p.id
        self._emit("PlantPlaced", p.id, plant_type=kind, row=row, col=col)

    def _remove_plant(self, pid: int, reason: str):
        p = self._plants.pop(pid, None)
        if p is not None:
            del self._tiles[p.row, p.col]
            self._emit("PlantRemoved", pid, reason=reason)

    def _sun_income(self, amount: int, source: str, entity_id: int | None = None):
        before = self._sun
        self._sun = min(self._g["sun_cap"], self._sun + amount)
        self._emit(
            "SunProduced", entity_id, source=source, amount=self._sun - before, produced=amount
        )

    def _advance(self):
        self._tick += 1
        for kind, value in self._cooldowns.items():
            if value:
                self._cooldowns[kind] = value - 1
        while (
            self._spawn_index < len(self._level.spawns)
            and self._level.spawns[self._spawn_index].tick <= self._tick
        ):
            spawn = self._level.spawns[self._spawn_index]
            spec = self.rules.zombies[spawn.zombie_type]
            pole = spawn.zombie_type == "pole_vaulting"
            z = _Zombie(
                self._id(),
                spawn.zombie_type,
                spawn.row,
                self._g["spawn_x"] if spawn.x is None else spawn.x,
                spec["health"],
                spec["armor"],
                "carrying_pole" if pole else "walking",
                has_pole=pole,
                speed=self._random(spec["speed"], spec["max_speed"]),
                pole_speed=self._random(spec["pole_speed"], spec["pole_max_speed"]) if pole else 0,
            )
            self._zombies[z.id] = z
            self._spawn_index += 1
            self._wave = max(self._wave, spawn.wave)
            self._emit("ZombieSpawned", z.id, zombie_type=z.kind, row=z.row, wave=spawn.wave)
        if self._tick >= self._sky_due:
            self._sun_income(self._g["sky_sun_amount"], "sky")
            self._sky_drops += 1
            self._sky_due = (
                self._tick
                + min(
                    self._g["sky_interval_max_ticks"],
                    self._g["sky_interval_base_ticks"]
                    + self._sky_drops * self._g["sky_interval_increment_ticks"],
                )
                + self._random(0, self._g["sky_interval_jitter_ticks"])
            )
        self._advance_plants()
        self._advance_projectiles()
        self._clear_dead()
        self._previous_x = {z.id: z.x for z in self._zombies.values()}
        self._advance_zombies()
        self._advance_mowers()
        self._clear_dead()
        for pid, p in list(self._plants.items()):
            if p.health <= 0:
                self._remove_plant(pid, "eaten")
        if any(not z.headless and z.x <= self._g["house_x"] for z in self._zombies.values()):
            self._status = Status.LOST
        elif self._defeated == len(self._level.spawns):
            self._status = Status.WON
        if self._status != Status.RUNNING:
            self._emit("GameEnded", outcome=self._status.value)

    def _center(self, p: _Plant) -> int:
        return p.col * self._g["units_per_tile"] + self._g["units_per_tile"] // 2

    def _targets(
        self, row: int, left: int, right: int | None = None, *, headed=False
    ) -> list[_Zombie]:
        return sorted(
            (
                z
                for z in self._zombies.values()
                if z.health > 0
                and z.row == row
                and z.x >= left
                and (right is None or z.x <= right)
                and (not headed or not z.headless)
            ),
            key=lambda z: (z.x, z.id),
        )

    def _damage(self, z: _Zombie, amount: int, source: int, *, swallow: bool = False):
        if z.health <= 0:
            return
        old_health, old_armor = z.health, z.armor
        if swallow:
            z.health = z.armor = 0
        else:
            absorbed = min(z.armor, amount)
            z.armor -= absorbed
            z.health = max(0, z.health - (amount - absorbed))
        self._emit(
            "DamageApplied",
            z.id,
            source=source,
            health_damage=old_health - z.health,
            armor_damage=old_armor - z.armor,
        )
        if not z.headless and z.health < self.rules.zombies[z.kind]["health"] // 3:
            z.headless = True
            z.has_pole = False
            z.bite_progress = z.target_id = 0
            self._defeated += 1
            self._emit("ZombieDefeated", z.id, zombie_type=z.kind, row=z.row)
            if z.health > 0:
                self._emit("ZombieHeadLost", z.id)

    def _clear_dead(self):
        for zid, z in list(self._zombies.items()):
            if z.health <= 0:
                z.state = "dead"
                del self._zombies[zid]
                self._emit("ZombieRemoved", zid)

    def _shoot(self, p: _Plant):
        spec = self.rules.plants[p.kind]
        shot = _Projectile(
            self._id(),
            p.row,
            self._center(p) + self._g["projectile_offset"],
            spec["damage"],
            p.kind == "snow_pea",
        )
        self._projectiles[shot.id] = shot
        self._emit("ProjectileFired", shot.id, source=p.id)

    def _detonate(self, p: _Plant):
        unit = self._g["units_per_tile"]
        p.state = "exploding" if p.kind == "cherry_bomb" else "detonating"
        radius = 1 if p.kind == "cherry_bomb" else 0
        left, right = (p.col - radius) * unit, (p.col + radius + 1) * unit
        for z in self._zombies.values():
            if abs(z.row - p.row) <= radius and left <= z.x < right:
                self._damage(z, self.rules.plants[p.kind]["damage"], p.id)
        self._emit("PlantExploded", p.id, row=p.row, col=p.col, radius=radius)
        self._remove_plant(p.id, "detonated")

    def _swallow(self, p: _Plant, z: _Zombie):
        self._damage(z, 0, p.id, swallow=True)
        p.state = "biting_got_one"
        spec = self.rules.plants[p.kind]
        p.due = self._tick + spec["bite_animation_ticks"] - spec["bite_ticks"]
        self._emit("ZombieSwallowed", z.id, source=p.id)

    def _advance_plants(self):
        unit = self._g["units_per_tile"]
        for p in list(self._plants.values()):
            spec = self.rules.plants[p.kind]
            center = self._center(p)
            if p.kind == "sunflower":
                if self._tick >= p.due:
                    self._sun_income(spec["sun_amount"], "sunflower", p.id)
                    p.due = self._tick + self._random(
                        spec["interval_ticks"], spec["interval_max_ticks"]
                    )
            elif p.kind in ("peashooter", "snow_pea", "repeater"):
                if p.burst_due and self._tick >= p.burst_due:
                    self._shoot(p)
                    p.burst_due = 0
                launch = self._tick >= p.due
                if launch:
                    p.due = (
                        self._tick
                        + spec["interval_ticks"]
                        - self._random(0, spec["interval_jitter_ticks"])
                    )
                if (
                    launch or (p.kind == "repeater" and p.due - self._tick == spec["burst_ticks"])
                ) and self._targets(p.row, center):
                    p.burst_due = self._tick + spec["windup_ticks"]
            elif p.kind == "cherry_bomb" and self._tick >= p.due:
                self._detonate(p)
            elif p.kind == "potato_mine":
                if p.state == "arming" and self._tick >= p.due:
                    p.state = "rising"
                    p.due = self._tick + spec["rise_ticks"]
                elif p.state == "rising" and self._tick >= p.due:
                    p.state = "armed"
                    self._emit("MineArmed", p.id)
                if p.state == "armed" and self._targets(
                    p.row, p.col * unit, (p.col + 1) * unit - 1, headed=True
                ):
                    self._detonate(p)
            elif p.kind == "chomper":
                if p.state == "biting" and self._tick >= p.due:
                    targets = self._targets(p.row, center, center + unit, headed=True)
                    if targets and not targets[0].has_pole and targets[0].state != "vaulting":
                        self._swallow(p, targets[0])
                    else:
                        p.state = "recovering"
                        p.due = self._tick + spec["bite_animation_ticks"] - spec["bite_ticks"]
                elif p.state == "biting_got_one" and self._tick >= p.due:
                    p.state = "digesting"
                    p.due = self._tick + spec["interval_ticks"]
                elif p.state == "digesting" and self._tick >= p.due:
                    p.state = "recovering"
                    p.due = self._tick + spec["recovery_ticks"]
                elif p.state == "recovering" and self._tick >= p.due:
                    p.state = "ready"
                if p.state == "ready":
                    targets = self._targets(p.row, center, center + unit, headed=True)
                    if targets:
                        p.state = "biting"
                        p.due = self._tick + spec["bite_ticks"]

    def _distance(self, entity, speed: int, *, slowed: bool = False) -> int:
        # A fixed denominator also preserves remainders when slow starts or expires.
        denominator = self._g["slow_denominator"]
        numerator = (
            speed * (self._g["slow_numerator"] if slowed else denominator) + entity.move_remainder
        )
        distance, entity.move_remainder = divmod(numerator, self._g["tick_rate"] * denominator)
        return distance

    def _advance_projectiles(self):
        for pid, shot in list(self._projectiles.items()):
            end = shot.x + self._distance(shot, self._g["projectile_speed"])
            targets = self._targets(shot.row, shot.x, end)
            if targets:
                z = targets[0]
                self._damage(z, shot.damage, shot.id)
                if shot.icy and z.health > 0:
                    z.slow_until = self._tick + self._g["slow_ticks"]
                    self._emit("SlowApplied", z.id, until=z.slow_until)
                del self._projectiles[pid]
            elif end > self._g["spawn_x"] + self._g["units_per_tile"]:
                del self._projectiles[pid]
            else:
                shot.x = end

    def _advance_zombies(self):
        for z in list(self._zombies.values()):
            if z.health <= 0:
                continue
            z.age += 1
            if z.headless and self._random(0, self._g["headless_decay_chance"] - 1) == 0:
                amount = (
                    self._g["headless_large_damage"]
                    if self.rules.zombies[z.kind]["health"] >= self._g["headless_large_health"]
                    else self._g["headless_damage"]
                )
                damage = min(z.health, amount)
                z.health -= damage
                self._emit("ZombieDecayed", z.id, damage=damage)
                if z.health <= 0:
                    continue
            if z.state == "vaulting":
                if self._tick < z.vault_until:
                    continue
                z.x = z.landing_x
                z.state = "walking"
                self._emit("VaultFinished", z.id)
            slowed = self._tick < z.slow_until
            speed = z.pole_speed if z.has_pole else z.speed
            end = z.x - self._distance(z, speed, slowed=slowed)
            # Nearest plant crossed while moving left, including the current bite target.
            blocking = sorted(
                (
                    p
                    for p in self._plants.values()
                    if p.row == z.row
                    and not z.headless
                    and p.health > 0
                    and end <= self._center(p) + self._g["contact_offset"] <= z.x
                ),
                key=lambda p: (-p.col, p.id),
            )
            if not blocking:
                self._move_zombie(z, end)
                z.state = "carrying_pole" if z.has_pole else "walking"
                z.bite_progress = z.target_id = 0
                continue
            p = blocking[0]
            self._move_zombie(z, self._center(p) + self._g["contact_offset"])
            if z.health <= 0 or z.headless:
                continue
            if p.kind == "potato_mine" and p.state == "armed":
                self._detonate(p)
                continue
            if z.has_pole:
                z.has_pole = False
                z.state = "vaulting"
                z.vault_until = self._tick + self._g["vault_ticks"]
                z.landing_x = z.x - self._g["vault_distance"]
                z.bite_progress = z.target_id = 0
                self._emit("VaultStarted", z.id, over=p.id)
                continue
            if z.target_id != p.id:
                z.bite_progress = 0
                z.target_id = p.id
            z.state = "biting"
            if (
                p.kind != "cherry_bomb"
                and z.age % (self._g["bite_ticks"] * (2 if slowed else 1)) == 0
            ):
                damage = min(p.health, self._g["bite_damage"])
                p.health -= damage
                self._emit("PlantDamaged", p.id, source=z.id, damage=damage)

    def _move_zombie(self, z: _Zombie, end: int):
        # Projectiles already moved this tick. Sweep the zombie's remaining motion
        # against them too, so two objects crossing between samples still collide.
        shots = sorted(
            (p for p in self._projectiles.values() if p.row == z.row and end <= p.x <= z.x),
            key=lambda p: (-p.x, p.id),
        )
        for shot in shots:
            self._damage(z, shot.damage, shot.id)
            if shot.icy and z.health > 0:
                z.slow_until = self._tick + self._g["slow_ticks"]
                self._emit("SlowApplied", z.id, until=z.slow_until)
            del self._projectiles[shot.id]
            if z.health <= 0:
                break
        z.x = end

    def _advance_mowers(self):
        for mower in self._mowers:
            if mower.state == "ready" and any(
                z.health > 0
                and not z.headless
                and z.row == mower.row
                and z.x <= self._g["mower_trigger_x"]
                for z in self._zombies.values()
            ):
                mower.state = "moving"
                mower.chomp_ticks = self._g["mower_first_hit_ticks"]
                self._emit("MowerActivated", row=mower.row)
                # Include every zombie that crossed the trigger in this same tick.
                for z in self._zombies.values():
                    if z.row == mower.row and z.x <= mower.x:
                        self._damage(z, 0, -mower.row - 1, swallow=True)
            if mower.state == "moving":
                speed = self._g["mower_speed"]
                if mower.chomp_ticks:
                    mower.chomp_ticks -= 1
                    span = self._g["mower_hit_ticks"]
                    speed = self._g["mower_min_speed"] + (
                        (speed - self._g["mower_min_speed"]) * (span - 2 * mower.chomp_ticks) ** 2
                    ) // (span * span)
                end = mower.x + self._distance(mower, speed)
                for z in self._zombies.values():
                    if (
                        z.row == mower.row
                        and z.health > 0
                        and z.x <= end
                        and self._previous_x.get(z.id, z.x) >= mower.x
                    ):
                        self._damage(z, 0, -mower.row - 1, swallow=True)
                        mower.chomp_ticks = self._g["mower_hit_ticks"]
                mower.x = end
                if mower.x > self._g["spawn_x"]:
                    mower.state = "spent"
                    self._emit("MowerSpent", row=mower.row)

    def observe(self) -> Observation:
        self._require_ready()
        g = self._g
        remaining = len(self._level.spawns) - self._defeated
        return Observation(
            API_VERSION,
            self._tick,
            self._tick / g["tick_rate"],
            g["tick_rate"],
            g["units_per_tile"],
            g["rows"],
            g["cols"],
            self._level.name,
            self._status,
            self._sun,
            tuple(
                CardView(
                    k,
                    self.rules.plants[k]["cost"],
                    self._cooldowns[k],
                    self.rules.plants[k]["recharge_ticks"],
                )
                for k in PLANT_TYPES
            ),
            tuple(
                PlantView(
                    p.id,
                    p.kind,
                    p.row,
                    p.col,
                    p.health,
                    self.rules.plants[p.kind]["health"],
                    p.state,
                    max(0, p.due - self._tick),
                )
                for p in self._plants.values()
            ),
            tuple(
                ZombieView(
                    z.id,
                    z.kind,
                    z.row,
                    z.x,
                    z.health,
                    z.armor,
                    z.state,
                    max(0, z.slow_until - self._tick),
                    z.has_pole,
                    max(0, z.vault_until - self._tick)
                    if z.state == "vaulting"
                    else (
                        max(0, self._g["bite_ticks"] * 2 - z.bite_progress)
                        + (0 if self._tick < z.slow_until else 1)
                    )
                    // (1 if self._tick < z.slow_until else 2)
                    if z.state == "biting"
                    else 0,
                    z.headless,
                )
                for z in self._zombies.values()
            ),
            tuple(
                ProjectileView(p.id, p.row, p.x, p.damage, p.icy)
                for p in self._projectiles.values()
            ),
            tuple(MowerView(m.row, m.x, m.state) for m in self._mowers),
            self._wave,
            self._total_waves,
            ZombieCounts(
                len(self._level.spawns),
                self._spawn_index,
                sum(not z.headless for z in self._zombies.values()),
                self._defeated,
                len(self._level.spawns) - self._spawn_index,
                remaining,
            ),
        )

    def snapshot(self) -> dict:
        """Detached JSON-safe internal state; deliberately contains future spawns."""
        self._require_ready()
        return {
            "snapshot_version": SNAPSHOT_VERSION,
            "engine_version": ENGINE_VERSION,
            "rules": self.rules.to_dict(),
            "rules_hash": self.rules.digest,
            "level": self._level.to_dict(),
            "seed": self._seed,
            "rng_state": copy.deepcopy(self._rng.getstate()),
            "gameplay_rng": self._gameplay_rng,
            "sky_due": self._sky_due,
            "sky_drops": self._sky_drops,
            "tick": self._tick,
            "status": self._status.value,
            "sun": self._sun,
            "cooldowns": dict(self._cooldowns),
            "next_id": self._next_id,
            "spawn_index": self._spawn_index,
            "defeated": self._defeated,
            "wave": self._wave,
            "plants": [asdict(p) for p in self._plants.values()],
            "zombies": [asdict(z) for z in self._zombies.values()],
            "projectiles": [asdict(p) for p in self._projectiles.values()],
            "mowers": [asdict(m) for m in self._mowers],
        }

    def state_hash(self) -> str:
        return canonical_hash(self.snapshot())

    def restore(self, snapshot: dict) -> Observation:
        """Atomically restore a compatible snapshot; failures preserve the current game."""
        data = copy.deepcopy(snapshot)
        if (
            data.get("snapshot_version") != SNAPSHOT_VERSION
            or data.get("engine_version") != ENGINE_VERSION
        ):
            raise ValueError("incompatible snapshot or engine version")
        if (
            data.get("rules_hash") != self.rules.digest
            or canonical_hash(data.get("rules")) != self.rules.digest
        ):
            raise ValueError("snapshot rules differ from this game's rules")
        candidate = Game(self.rules)
        try:
            candidate.reset(LevelSpec.from_dict(data["level"]), data["seed"])
            candidate._tick = integer(data["tick"], "tick")
            candidate._status = Status(data["status"])
            candidate._sun = integer(data["sun"], "sun")
            candidate._cooldowns = dict(data["cooldowns"])
            if set(candidate._cooldowns) != set(PLANT_TYPES):
                raise ValueError("invalid cooldown keys")
            for k, v in candidate._cooldowns.items():
                integer(v, "cooldown")
                if v > self.rules.plants[k]["recharge_ticks"] + 1:
                    raise ValueError("cooldown exceeds recharge")
            for attr in (
                "next_id",
                "spawn_index",
                "defeated",
                "wave",
                "gameplay_rng",
                "sky_due",
                "sky_drops",
            ):
                setattr(candidate, "_" + attr, integer(data[attr], attr))
            candidate._plants = {p["id"]: _Plant(**p) for p in data["plants"]}
            candidate._zombies = {z["id"]: _Zombie(**z) for z in data["zombies"]}
            candidate._projectiles = {p["id"]: _Projectile(**p) for p in data["projectiles"]}
            candidate._mowers = [_Mower(**m) for m in data["mowers"]]
            candidate._tiles = {(p.row, p.col): p.id for p in candidate._plants.values()}
            candidate._rng.setstate(_tuples(data["rng_state"]))
            candidate._check_snapshot(data)
        except (KeyError, TypeError, IndexError, AssertionError) as exc:
            raise ValueError(f"malformed snapshot: {exc}") from exc
        self.__dict__.update(candidate.__dict__)
        return self.observe()

    def _check_snapshot(self, raw: dict):
        g = self._g
        ids = [
            e.id
            for group in (self._plants, self._zombies, self._projectiles)
            for e in group.values()
        ]
        if len(ids) != sum(len(raw[k]) for k in ("plants", "zombies", "projectiles")):
            raise ValueError("duplicate entity IDs")
        if len(ids) != len(set(ids)) or any(type(i) is not int or i <= 0 for i in ids):
            raise ValueError("invalid entity IDs")
        if self._next_id <= max(ids, default=0) or self._sun > g["sun_cap"]:
            raise ValueError("invalid next ID or sun")
        if not 0 < self._gameplay_rng <= 0xFFFFFFFF or self._sky_due <= self._tick:
            raise ValueError("invalid gameplay RNG or sky countdown")
        if self._spawn_index > len(self._level.spawns) or self._spawn_index != self._defeated + sum(
            not z.headless for z in self._zombies.values()
        ):
            raise ValueError("inconsistent zombie counts")
        expected_spawns = sum(s.tick <= self._tick for s in self._level.spawns)
        if self._spawn_index != expected_spawns:
            raise ValueError("spawn index does not match tick")
        if len(self._tiles) != len(self._plants):
            raise ValueError("multiple plants in a tile")
        for p in self._plants.values():
            if (
                p.kind not in self.rules.plants
                or not 0 <= p.row < g["rows"]
                or not 0 <= p.col < g["cols"]
                or p.health <= 0
                or p.health > self.rules.plants[p.kind]["health"]
                or p.state
                not in (
                    "ready",
                    "arming",
                    "armed",
                    "fusing",
                    "digesting",
                    "rising",
                    "biting",
                    "biting_got_one",
                    "recovering",
                )
            ):
                raise ValueError("invalid plant state")
        for z in self._zombies.values():
            if (
                z.kind not in self.rules.zombies
                or not 0 <= z.row < g["rows"]
                or z.health <= 0
                or z.health > self.rules.zombies[z.kind]["health"]
                or not 0 <= z.armor <= self.rules.zombies[z.kind]["armor"]
                or z.state not in ("walking", "biting", "carrying_pole", "vaulting")
            ):
                raise ValueError("invalid zombie state")
        if (
            len(self._mowers) != g["rows"]
            or {m.row for m in self._mowers} != set(range(g["rows"]))
            or any(m.state not in ("ready", "moving", "spent") for m in self._mowers)
        ):
            raise ValueError("invalid mowers")
        if self._status == Status.WON and self._defeated != len(self._level.spawns):
            raise ValueError("victory with zombies remaining")
        expected_wave = max((s.wave for s in self._level.spawns[: self._spawn_index]), default=0)
        if self._wave != expected_wave:
            raise ValueError("wave index does not match spawned zombies")
        for group in (
            self._plants.values(),
            self._zombies.values(),
            self._projectiles.values(),
            self._mowers,
        ):
            for entity in group:
                for key, value in asdict(entity).items():
                    if key in ("kind", "state"):
                        continue
                    if key in ("icy", "has_pole", "headless"):
                        if type(value) is not bool:
                            raise ValueError(f"{key} must be boolean")
                    elif type(value) is not int:
                        raise ValueError(f"{key} must be integer")
                    elif key not in ("x", "landing_x") and value < 0:
                        raise ValueError(f"{key} must be nonnegative")
                if hasattr(entity, "move_remainder") and not (
                    0 <= entity.move_remainder < g["tick_rate"] * g["slow_denominator"]
                ):
                    raise ValueError("invalid movement remainder")
        for p in self._plants.values():
            allowed = {
                "potato_mine": ("arming", "rising", "armed"),
                "cherry_bomb": ("fusing",),
                "chomper": ("ready", "biting", "biting_got_one", "digesting", "recovering"),
            }.get(p.kind, ("ready",))
            if p.state not in allowed:
                raise ValueError("plant state does not match type")
        for z in self._zombies.values():
            if z.bite_progress >= g["bite_ticks"] * 2:
                raise ValueError("invalid bite progress")
            if (
                z.has_pole or z.state in ("carrying_pole", "vaulting")
            ) and z.kind != "pole_vaulting":
                raise ValueError("only pole zombies can vault")
        for p in self._projectiles.values():
            if not 0 <= p.row < g["rows"] or p.damage < 0:
                raise ValueError("invalid projectile")
        breached = any(not z.headless and z.x <= g["house_x"] for z in self._zombies.values())
        if (self._status == Status.LOST) != breached:
            raise ValueError("game outcome does not match house boundary")


def _tuples(value):
    return tuple(_tuples(v) for v in value) if isinstance(value, (list, tuple)) else value
