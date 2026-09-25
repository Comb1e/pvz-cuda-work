"""CuPy/NVRTC implementation with explicit storage limits and diagnostic transfers.

No host observation or snapshot is constructed by ``step_device``. The methods
ending in ``_device`` accept trusted, contiguous device inputs; checked public
entry points synchronize to diagnose invalid callers before changing any state.
"""

from __future__ import annotations

import copy
import math
import os
import sys
from importlib.resources import files
from pathlib import Path

from ..config import PLANT_TYPES, ZOMBIE_TYPES, Rules, canonical_hash
from ..engine import Game
from ..types import Event, GameFinishedError
from . import schema as s


class CapacityError(ValueError):
    """A scenario or snapshot exceeds a declared storage bound; no state changed."""


_dll_handles = []


def cupy_runtime():
    """Find a toolkit or PyTorch's bundled CUDA DLLs without changing installations."""
    import importlib.metadata

    # NVIDIA's runtime/NVRTC wheels provide headers and DLLs without nvcc or a
    # machine-wide toolkit. Keep this process-local; never alter system settings.
    for package, directory in (
        ("nvidia-cuda-runtime-cu12", "cuda_runtime"),
        ("nvidia-cuda-nvrtc-cu12", "cuda_nvrtc"),
    ):
        try:
            root = Path(importlib.metadata.distribution(package).locate_file(f"nvidia/{directory}"))
        except importlib.metadata.PackageNotFoundError:
            continue
        if directory == "cuda_runtime" and not os.environ.get("CUDA_PATH"):
            os.environ["CUDA_PATH"] = str(root)
        if sys.platform == "win32":
            lib = root / "bin"
            if lib.is_dir() and str(lib) not in os.environ.get("PATH", "").split(os.pathsep):
                _dll_handles.append(os.add_dll_directory(str(lib)))
                os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
    if sys.platform == "win32" and not _dll_handles:
        import importlib.util

        spec = importlib.util.find_spec("torch")
        if spec and spec.submodule_search_locations:
            lib = Path(next(iter(spec.submodule_search_locations))) / "lib"
            if lib.is_dir():
                _dll_handles.append(os.add_dll_directory(str(lib)))
                # CuPy's ctypes DLL discovery also consults PATH on Windows.
                os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
    try:
        import cupy as cp
    except ImportError as exc:
        raise RuntimeError(
            "CUDA simulator requires the optional cupy-cuda12x==13.6.0 package"
        ) from exc
    if cp.__version__ != "13.6.0":
        raise RuntimeError("CUDA backend schema 1 requires CuPy 13.6.0")
    return cp


def projectile_bound(rules):
    """Bound every live shot, including rapid replacement and simultaneous bursts.

    A shot lives at most L ticks. A tile fires at most twice per tick, even if
    repeatedly dug/replanted with infinite sun. Thus 2*45*(L+1) bounds storage
    before projectile advancement without assuming recharge or finite sun.
    """
    g = rules.game
    distance = (
        g["spawn_x"] + g["units_per_tile"] - g["units_per_tile"] // 2 - g["projectile_offset"]
    )
    lifetime = math.ceil((distance + 1) * g["tick_rate"] / g["projectile_speed"])
    return 2 * g["rows"] * g["cols"] * (lifetime + 1)


def kernel_source(rules, zombie_capacity, projectile_capacity, event_capacity, diagnostic):
    prefix = ["typedef long long I;"]
    prefix.extend(f"#define G_{k} {v}LL" for k, v in rules.game.items())
    prefix.extend(
        f"#define GAME_{name}_WIDTH {len(fields)}"
        for name, fields in (
            ("HEADER", s.HEADER),
            ("PLANT", s.PLANT),
            ("ZOMBIE", s.ZOMBIE),
            ("PROJECTILE", s.PROJECTILE),
            ("MOWER", s.MOWER),
        )
    )
    prefix.extend(
        f"#define {k} {int(v)}"
        for k, v in {
            "ZCAP": zombie_capacity,
            "QCAP": projectile_capacity,
            "ECAP": event_capacity,
            "DIAGNOSTIC": diagnostic,
        }.items()
    )
    arrays = {
        "PC": (rules.plants, PLANT_TYPES, "cost"),
        "PH": (rules.plants, PLANT_TYPES, "health"),
        "PF": (rules.plants, PLANT_TYPES, "first_ticks"),
        "PI": (rules.plants, PLANT_TYPES, "interval_ticks"),
        "PB": (rules.plants, PLANT_TYPES, "burst_ticks"),
        "PR": (rules.plants, PLANT_TYPES, "recharge_ticks"),
        "PD": (rules.plants, PLANT_TYPES, "damage"),
        "PS": (rules.plants, PLANT_TYPES, "sun_amount"),
        "PFMAX": (rules.plants, PLANT_TYPES, "first_max_ticks"),
        "PIMAX": (rules.plants, PLANT_TYPES, "interval_max_ticks"),
        "PJ": (rules.plants, PLANT_TYPES, "interval_jitter_ticks"),
        "PW": (rules.plants, PLANT_TYPES, "windup_ticks"),
        "PRISE": (rules.plants, PLANT_TYPES, "rise_ticks"),
        "PBITE": (rules.plants, PLANT_TYPES, "bite_ticks"),
        "PANIM": (rules.plants, PLANT_TYPES, "bite_animation_ticks"),
        "PRECOVER": (rules.plants, PLANT_TYPES, "recovery_ticks"),
        "ZH": (rules.zombies, ZOMBIE_TYPES, "health"),
        "ZA": (rules.zombies, ZOMBIE_TYPES, "armor"),
        "ZS": (rules.zombies, ZOMBIE_TYPES, "speed"),
        "ZP": (rules.zombies, ZOMBIE_TYPES, "pole_speed"),
        "ZSMAX": (rules.zombies, ZOMBIE_TYPES, "max_speed"),
        "ZPMAX": (rules.zombies, ZOMBIE_TYPES, "pole_max_speed"),
    }
    for name, (group, kinds, key) in arrays.items():
        values = [group[k].get(key, group[k].get("speed", 0) if name == "ZP" else 0) for k in kinds]
        prefix.append(f"__device__ __constant__ I {name}[] = {{{','.join(map(str, values))}}};")
    return (
        "\n".join(prefix) + "\n" + files(__package__).joinpath("simulation.cu").read_text("utf-8")
    )


class CudaBatch:
    """Many independent pinned-rule games on one CUDA device.

    Allocate from the largest resolved scenario in the workload. Reset validates
    the complete submitted batch before transferring anything. The CPU engine is
    used only to resolve/validate initial state and for explicit diagnostics.
    """

    def __init__(
        self,
        num_games,
        *,
        zombie_capacity,
        projectile_capacity=None,
        diagnostic=False,
        max_step_ticks=10,
        rules=None,
        device=0,
    ):
        self.rules = rules or Rules()
        if self.rules.digest != Rules().digest:
            raise ValueError("Modified combat rules require the CPU simulator")
        for value in (num_games, zombie_capacity, max_step_ticks):
            if type(value) is not int or value < 1:
                raise ValueError("Batch size and capacities must be positive integers")
        minimum = projectile_bound(self.rules)
        if projectile_capacity is not None and (
            type(projectile_capacity) is not int or projectile_capacity < minimum
        ):
            raise CapacityError(f"Projectile capacity must be >= the proved bound {minimum}")
        self.n, self.zcap, self.qcap = num_games, zombie_capacity, projectile_capacity or minimum
        self.max_step_ticks, self.diagnostic, self.device = max_step_ticks, diagnostic, device
        self.ecap = max_step_ticks * (16 * (self.zcap + self.qcap + 45) + 64) if diagnostic else 1
        self.cp = cp = cupy_runtime()
        cp.cuda.Device(device).use()
        self.header = cp.zeros((num_games, len(s.HEADER)), dtype=cp.int64)
        self.plants = cp.zeros((num_games, 45, len(s.PLANT)), dtype=cp.int64)
        self.zombies = cp.zeros((num_games, self.zcap, len(s.ZOMBIE)), dtype=cp.int64)
        self.projectiles = cp.zeros((num_games, self.qcap, len(s.PROJECTILE)), dtype=cp.int64)
        self.mowers = cp.zeros((num_games, 5, len(s.MOWER)), dtype=cp.int64)
        self.cooldowns = cp.zeros((num_games, 8), dtype=cp.int64)
        self._schedules = cp.zeros((num_games, self.zcap, 5), dtype=cp.int64)
        self._events = cp.zeros((num_games, self.ecap, 8), dtype=cp.int64)
        self._event_counts = cp.zeros(num_games, dtype=cp.int64)
        self.facts = cp.zeros((num_games, len(s.FACTS)), dtype=cp.float64)
        self.masks = cp.zeros((num_games, 406), dtype=cp.bool_)
        self._templates = [None] * num_games
        self.source = kernel_source(self.rules, self.zcap, self.qcap, self.ecap, diagnostic)
        self.module = cp.RawModule(code=self.source, options=("--std=c++11", "--fmad=false"))
        self._step = self.module.get_function("step_games")
        self._mask = self.module.get_function("legal_masks")

    def _indices(self, indices):
        indices = list(range(self.n)) if indices is None else list(indices)
        if len(set(indices)) != len(indices) or any(
            type(i) is not int or not 0 <= i < self.n for i in indices
        ):
            raise ValueError("Reset indices must be unique games in this batch")
        return indices

    def reset(self, levels, seeds, *, indices=None, allowed=None, digging=None):
        indices = self._indices(indices)
        if len(levels) != len(indices) or len(seeds) != len(indices):
            raise ValueError("One level and seed required for every reset index")
        snapshots = []
        for level, seed in zip(levels, seeds):
            game = Game(self.rules)
            game.reset(level, seed)
            snapshots.append(game.snapshot())
        self.restore(snapshots, indices=indices, allowed=allowed, digging=digging)

    def restore(self, snapshots, *, indices=None, allowed=None, digging=None):
        import numpy as np

        indices = self._indices(indices)
        if len(snapshots) != len(indices):
            raise ValueError("One snapshot required per index")
        allowed = [255] * len(indices) if allowed is None else list(allowed)
        digging = [True] * len(indices) if digging is None else list(digging)
        if (
            len(allowed) != len(indices)
            or len(digging) != len(indices)
            or any(type(x) is not int or not 0 <= x <= 255 for x in allowed)
            or any(type(x) is not bool for x in digging)
        ):
            raise ValueError("Invalid per-game task restrictions")
        groups = ("plants", "zombies", "projectiles", "mowers")
        schemas = (s.PLANT, s.ZOMBIE, s.PROJECTILE, s.MOWER)
        staged = []
        for snapshot, allow, dig in zip(snapshots, allowed, digging):
            game = Game(self.rules)
            game.restore(snapshot)
            raw = game.snapshot()
            if len(raw["level"]["spawns"]) > self.zcap:
                raise CapacityError(
                    f"Scenario requires {len(raw['level']['spawns'])} zombie slots, allocated {self.zcap}"
                )
            # Arbitrary restored shots may exceed the reachable-state proof. Reserve
            # their entire remaining lifetime in addition to the proved new-shot bound.
            if raw["tick"] and len(raw["projectiles"]) + projectile_bound(self.rules) > self.qcap:
                raise CapacityError("Restored mid-game state needs extra projectile headroom")
            header = np.zeros(len(s.HEADER), dtype=np.int64)
            fields = {
                **raw,
                "status": s.STATUSES.index(raw["status"]),
                "total_waves": max((x["wave"] for x in raw["level"]["spawns"]), default=0),
                "total_spawns": len(raw["level"]["spawns"]),
                "np": len(raw["plants"]),
                "nz": len(raw["zombies"]),
                "nq": len(raw["projectiles"]),
                "allowed": allow,
                "dig": dig,
                "enabled": 1,
            }
            for j, field in enumerate(s.HEADER):
                header[j] = fields.get(field, 0)
            arrays = []
            for group, schema in zip(groups, schemas):
                array = np.zeros(getattr(self, group).shape[1:], dtype=np.int64)
                for j, item in enumerate(raw[group]):
                    item = dict(item)
                    if group in ("plants", "zombies"):
                        item["kind"] = (PLANT_TYPES if group == "plants" else ZOMBIE_TYPES).index(
                            item["kind"]
                        )
                    if "state" in item:
                        states = {
                            "plants": s.PLANT_STATES,
                            "zombies": s.ZOMBIE_STATES,
                            "mowers": s.MOWER_STATES,
                        }[group]
                        item["state"] = states.index(item["state"])
                    array[j] = [item.get(k, 0) for k in schema]
                arrays.append(array)
            schedule = np.zeros((self.zcap, 5), dtype=np.int64)
            for j, spawn in enumerate(raw["level"]["spawns"]):
                schedule[j] = (
                    spawn["tick"],
                    ZOMBIE_TYPES.index(spawn["zombie_type"]),
                    spawn["row"],
                    spawn["wave"],
                    self.rules.game["spawn_x"] if spawn["x"] is None else spawn["x"],
                )
            staged.append(
                (raw, header, arrays, schedule, [raw["cooldowns"][k] for k in PLANT_TYPES])
            )
        # Every validation/allocation above precedes the first mutation.
        cp = self.cp
        for index, (raw, header, arrays, schedule, cooldowns) in zip(indices, staged):
            self._templates[index] = raw
            self.header[index] = cp.asarray(header)
            for group, value in zip(groups, arrays):
                getattr(self, group)[index] = cp.asarray(value)
            self._schedules[index] = cp.asarray(schedule)
            self.cooldowns[index] = cp.asarray(cooldowns, dtype=cp.int64)
            self.facts[index] = 0
            self._event_counts[index] = 0
        self.action_masks_device()

    def step_device(self, actions, *, ticks=1, per_tick=True):
        """Trusted collector path. Caller keeps inputs/outputs on the current stream."""
        if type(ticks) is not int or not 1 <= ticks <= self.max_step_ticks:
            raise ValueError(f"ticks must be between 1 and {self.max_step_ticks}")
        if (
            actions.shape != (self.n,)
            or actions.dtype != self.cp.int64
            or not actions.flags.c_contiguous
        ):
            raise ValueError("Actions must be contiguous int64[num_games] on this device")
        self._step(
            (self.n,),
            (32,),
            (
                self.header,
                self.plants,
                self.zombies,
                self.projectiles,
                self.mowers,
                self.cooldowns,
                self._schedules,
                self._events,
                self._event_counts,
                self.facts,
                actions,
                self.n,
                ticks,
                int(per_tick),
            ),
        )
        return self.header, self.facts

    def step(self, actions, *, ticks=1, per_tick=True):
        import numpy as np

        values = np.asarray(actions)
        if (
            values.shape != (self.n,)
            or values.dtype.kind not in "iu"
            or np.any(values < 0)
            or np.any(values >= 406)
        ):
            raise ValueError("Actions must be integers in Discrete(406), one per game")
        header = self.header.get()
        if any(x is None for x in self._templates):
            raise RuntimeError("Reset every game before stepping")
        if np.any((header[:, 1] != 0) & (header[:, 17] != 0)):
            raise GameFinishedError("Reset completed games before stepping")
        return self.step_device(
            self.cp.asarray(values, dtype=self.cp.int64), ticks=ticks, per_tick=per_tick
        )

    def action_masks_device(self):
        self._mask(
            ((self.n * 406 + 255) // 256,),
            (256,),
            (self.header, self.plants, self.cooldowns, self.masks, self.n),
        )
        return self.masks

    def public_state_device(self):
        """Numeric present-state arrays. Schedules, templates and seeds stay private.

        Encoder implementations must select documented public fields: internal
        identity/timer fields are retained here for simulation diagnostics only.
        This is a backend interface, never a policy observation.
        """
        return {
            k: getattr(self, k)
            for k in ("header", "plants", "zombies", "projectiles", "mowers", "cooldowns")
        }

    def snapshot(self, index):
        raw = copy.deepcopy(self._templates[index])
        if raw is None:
            raise RuntimeError("Reset before taking snapshots")
        header = dict(zip(s.HEADER, self.header[index].get().tolist()))
        for key in (
            "tick",
            "sun",
            "next_id",
            "spawn_index",
            "defeated",
            "wave",
            "gameplay_rng",
            "sky_due",
            "sky_drops",
        ):
            raw[key] = header[key]
        raw["status"] = s.STATUSES[header["status"]]
        raw["cooldowns"] = dict(zip(PLANT_TYPES, self.cooldowns[index].get().tolist()))
        for group, schema, count, states, kinds in (
            ("plants", s.PLANT, header["np"], s.PLANT_STATES, PLANT_TYPES),
            ("zombies", s.ZOMBIE, header["nz"], s.ZOMBIE_STATES, ZOMBIE_TYPES),
            ("projectiles", s.PROJECTILE, header["nq"], None, None),
            ("mowers", s.MOWER, 5, s.MOWER_STATES, None),
        ):
            raw[group] = []
            for row in getattr(self, group)[index, :count].get().tolist():
                item = dict(zip(schema, row))
                item.pop("previous_x", None)
                if kinds:
                    item["kind"] = kinds[item["kind"]]
                if states:
                    item["state"] = states[item["state"]]
                for key in ("icy", "has_pole", "headless"):
                    if key in item:
                        item[key] = bool(item[key])
                raw[group].append(item)
        return raw

    def state_hash(self, index):
        return canonical_hash(self.snapshot(index))

    def observe(self, index):
        game = Game(self.rules)
        return game.restore(self.snapshot(index))

    def events(self, index):
        if not self.diagnostic:
            raise RuntimeError("Detailed events require diagnostic=True")
        count = int(self._event_counts[index].get())
        result = []
        for row in self._events[index, :count].get().tolist():
            kind, tick, entity, *args = row
            name, keys = s.EVENTS[kind]
            details = dict(zip(keys, args))
            for key, values in (
                ("plant_type", PLANT_TYPES),
                ("zombie_type", ZOMBIE_TYPES),
                ("outcome", s.STATUSES),
            ):
                if key in details:
                    details[key] = values[details[key]]
            if name == "PlantRemoved":
                details["reason"] = ("dug", "detonated", "eaten")[details["reason"]]
            if name == "ActionRejected":
                details["reason"] = s.REASONS[details["reason"]]
            if name == "SunProduced":
                details["source"] = ("sky", "sunflower")[details["source"]]
            result.append(Event(name, tick, entity or None, tuple(sorted(details.items()))))
        return tuple(result)
