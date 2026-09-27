"""Shared numerical geometry and fixed-point gait specification (no artwork)."""

from .config import bundled

SPEC = bundled("mechanics.toml")
GAITS = tuple(tuple(g["deltas"]) for g in SPEC["gaits"])
SCALE = SPEC["phase_scale"]
MOVE_DENOMINATOR = 100 * 10 * SPEC["source_tile_pixels"] * SCALE
PIXELS = SPEC["source_tile_pixels"]


def bite_immune(kind, state):
    # EatPlant starts eating before checking these damage immunities.
    return kind == "cherry_bomb" or (kind == "potato_mine" and state != "arming")


def gait_step(z, units, chilled):
    deltas = GAITS[z.gait]
    frames = len(deltas) + 1
    rate = z.speed * frames * SPEC["animation_factor"] * SCALE // (100 * sum(deltas))
    if chilled:
        rate //= 2
    # Keep normalized phase continuous, including the final interval and wrap.
    index = z.gait_phase * len(deltas) // SCALE
    distance, z.move_remainder = divmod(
        deltas[index] * rate * units + z.move_remainder, MOVE_DENOMINATOR
    )
    advance, z.phase_remainder = divmod(rate + z.phase_remainder, 100 * frames)
    z.gait_phase = (z.gait_phase + advance) % SCALE
    return distance


def overlap(left_a, right_a, left_b, right_b):
    """Return the positive overlap of two half-open source-coordinate intervals."""
    return max(0, min(right_a, right_b) - max(left_a, left_b))


def attack_contact(
    col, zombie_x, units, pole=False, *, minimum_pixels=SPEC["contact_overlap_pixels"]
):
    """Whether a zombie body overlaps a plant's attack rectangle enough to bite."""
    plant_left = (col * PIXELS + SPEC["plant_inset_pixels"]) * units
    plant_right = plant_left + SPEC["plant_width_pixels"] * units
    offset = SPEC["pole_attack_offset_pixels" if pole else "attack_offset_pixels"]
    width = SPEC["pole_attack_width_pixels" if pole else "attack_width_pixels"]
    attack_left = zombie_x * PIXELS + offset * units
    return (
        overlap(plant_left, plant_right, attack_left, attack_left + width * units)
        >= minimum_pixels * units
    )


def projectile_contact(zombie_x, shot_start, shot_end, units):
    """Positive rectangle overlap for a swept pea and zombie body.

    Equality is deliberately a miss: a projectile touching one edge has zero
    area and the PC collision routine rejects that contact.
    """
    return swept_projectile_contact(zombie_x, zombie_x, shot_start, shot_end, units)


def swept_projectile_contact(zombie_start, zombie_end, shot_start, shot_end, units):
    """Positive overlap for both swept rectangles."""
    zombie_left = min(zombie_start, zombie_end) * PIXELS
    zombie_right = max(zombie_start, zombie_end) * PIXELS + SPEC["body_width_pixels"] * units
    shot_left = min(shot_start, shot_end) * PIXELS - SPEC["projectile_back_pixels"] * units
    shot_right = max(shot_start, shot_end) * PIXELS + SPEC["projectile_front_pixels"] * units
    return overlap(zombie_left, zombie_right, shot_left, shot_right) > 0


def mower_contact(zombie_start, zombie_end, mower_x, units):
    """Positive swept overlap with the 50px mower body interval."""
    body_left = min(zombie_start, zombie_end) * PIXELS
    body_right = max(zombie_start, zombie_end) * PIXELS + SPEC["body_width_pixels"] * units
    mower_left = mower_x * PIXELS - SPEC["mower_width_pixels"] * units
    mower_right = mower_x * PIXELS
    return overlap(body_left, body_right, mower_left, mower_right) > 0


def blast_hits(col, row, x, zombie_row, units, cherry):
    if abs(row - zombie_row) > int(cherry):
        return False
    cx = col * units * 80 + (40 if cherry else 20) * units
    cy = (row * 100 + 40) * units
    left, right = x * 80, x * 80 + 42 * units
    top, bottom = (zombie_row * 100 - 30) * units, (zombie_row * 100 + 85) * units
    dx, dy = max(left - cx, 0, cx - right), max(top - cy, 0, cy - bottom)
    return dx * dx + dy * dy <= ((115 if cherry else 60) * units) ** 2


def cuda_constants():
    lines = [f"#define M_{k} {v}LL" for k, v in SPEC.items() if isinstance(v, int)]
    lines.append(f"#define M_move_denominator {MOVE_DENOMINATOR}LL")
    lines.append(
        "__device__ __constant__ I GN[] = {" + ",".join(str(len(x) + 1) for x in GAITS) + "};"
    )
    lines.append("__device__ __constant__ I GD[] = {" + ",".join(str(sum(x)) for x in GAITS) + "};")
    lines.append(
        "__device__ __constant__ I GDELTA[4][46] = {"
        + ",".join("{" + ",".join(map(str, x)) + "}" for x in GAITS)
        + "};"
    )
    return "\n".join(lines)
