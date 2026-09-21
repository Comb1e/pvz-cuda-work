"""Versioned numeric storage and public event schema shared with CUDA kernels."""

SCHEMA_VERSION = 1
HEADER = "tick status sun next_id spawn_index defeated wave total_waves total_spawns np nz nq accepted reason advanced allowed dig enabled".split()
PLANT = "id kind row col health state due burst_due".split()
ZOMBIE = "id kind row x health armor state slow_until has_pole vault_until landing_x bite_progress move_remainder target_id previous_x".split()
PROJECTILE = "id row x damage icy move_remainder".split()
MOWER = "row x state move_remainder".split()
PLANT_STATES = ("ready", "arming", "armed", "fusing", "digesting", "exploding", "detonating")
ZOMBIE_STATES = ("walking", "carrying_pole", "vaulting", "biting", "dead")
MOWER_STATES = ("ready", "moving", "spent")
STATUSES = ("running", "won", "lost")
REASONS = (
    None,
    "occupied_tile",
    "card_recharging",
    "insufficient_sun",
    "empty_tile",
    "task_restriction",
    "game_finished",
    "outside_space",
)
# Each event is kind, tick, entity_id (0 means None), then five typed arguments.
EVENTS = (
    ("PlantPlaced", ("plant_type", "row", "col")),
    ("PlantRemoved", ("reason",)),
    ("ActionRejected", ("reason",)),
    ("ZombieSpawned", ("zombie_type", "row", "wave")),
    ("SunProduced", ("source", "amount", "produced")),
    ("DamageApplied", ("source", "health_damage", "armor_damage")),
    ("ZombieDefeated", ("zombie_type", "row")),
    ("ProjectileFired", ("source",)),
    ("PlantExploded", ("row", "col", "radius")),
    ("ZombieSwallowed", ("source",)),
    ("MineArmed", ()),
    ("SlowApplied", ("until",)),
    ("VaultFinished", ()),
    ("VaultStarted", ("over",)),
    ("PlantDamaged", ("source", "damage")),
    ("MowerActivated", ("row",)),
    ("MowerSpent", ("row",)),
    ("GameEnded", ("outcome",)),
)
FACTS = "plant_kills mower_kills nonlethal_health_damage nonlethal_damage_fraction empty_mower_activations mower_activations mower_activation_sun wall_nut_damage empty_explosions".split()
