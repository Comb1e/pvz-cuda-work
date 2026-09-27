"""Shared numerical geometry and fixed-point gait specification (no artwork)."""

from .config import bundled

SPEC = bundled("mechanics.toml")
GAITS = tuple(tuple(g["deltas"]) for g in SPEC["gaits"])
SCALE = SPEC["phase_scale"]
MOVE_DENOMINATOR = 100 * 10 * SPEC["source_tile_pixels"] * SCALE
SOURCE_VELOCITY_SCALE = SPEC["source_velocity_scale"]


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


def contact_interval(col, units, pole):
    # Cross-multiplied source pixels; public x is the body rectangle's left edge.
    offset = SPEC["pole_attack_offset_pixels" if pole else "attack_offset_pixels"]
    width = SPEC["pole_attack_width_pixels" if pole else "attack_width_pixels"]
    left = col * units * 80 + (10 + 20 - offset - width) * units
    right = col * units * 80 + (70 - 20 - offset) * units
    return left, right


def overlap(left_a, right_a, left_b, right_b):
    """Return the positive overlap of two half-open source-coordinate intervals."""
    return max(0, min(right_a, right_b) - max(left_a, left_b))


def body_interval(x, units):
    """The public zombie x is the left edge of its 42px body rectangle."""
    return x * 80, x * 80 + 42 * units


def attack_contact(col, zombie_x, units, pole=False, *, minimum_pixels=20):
    """Whether a zombie body overlaps a plant's attack rectangle enough to bite."""
    plant_left = col * 80 * units + 10 * units
    plant_right = col * 80 * units + 70 * units
    offset = SPEC["pole_attack_offset_pixels" if pole else "attack_offset_pixels"]
    width = SPEC["pole_attack_width_pixels" if pole else "attack_width_pixels"]
    attack_left = zombie_x * 80 + offset * units
    return overlap(plant_left, plant_right, attack_left, attack_left + width * units) >= minimum_pixels * units


def swept_attack_contact(col, start_x, end_x, units, pole=False, *, minimum_pixels=20):
    """Whether a left-moving body reaches a plant attack rectangle this tick."""
    plant_left = col * 80 * units + 10 * units
    plant_right = col * 80 * units + 70 * units
    offset = SPEC["pole_attack_offset_pixels" if pole else "attack_offset_pixels"]
    width = SPEC["pole_attack_width_pixels" if pole else "attack_width_pixels"]
    attack_left = min(start_x, end_x) * 80 + offset * units
    attack_right = max(start_x, end_x) * 80 + offset * units + width * units
    return overlap(plant_left, plant_right, attack_left, attack_right) >= minimum_pixels * units


def projectile_contact(zombie_x, shot_start, shot_end, units):
    """Positive rectangle overlap for a swept pea and zombie body.

    Equality is deliberately a miss: a projectile touching one edge has zero
    area and the PC collision routine rejects that contact.
    """
    return swept_projectile_contact(zombie_x, zombie_x, shot_start, shot_end, units)


def swept_projectile_contact(zombie_start, zombie_end, shot_start, shot_end, units):
    """Positive overlap for both swept rectangles."""
    zombie_left = min(zombie_start, zombie_end) * 80
    zombie_right = max(zombie_start, zombie_end) * 80 + 42 * units
    shot_left = min(shot_start, shot_end) * 80 - 15 * units
    shot_right = max(shot_start, shot_end) * 80 + 40 * units
    return overlap(zombie_left, zombie_right, shot_left, shot_right) > 0


def mower_contact(zombie_start, zombie_end, mower_x, units):
    """Positive swept overlap with the 50px mower body interval."""
    body_left = min(zombie_start, zombie_end) * 80
    body_right = max(zombie_start, zombie_end) * 80 + 42 * units
    mower_left = mower_x * 80 - 50 * units
    mower_right = mower_x * 80
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
