"""Shared numerical geometry and fixed-point gait specification (no artwork)."""

from .config import bundled

SPEC = bundled("mechanics.toml")
GAITS = tuple(tuple(g["deltas"]) for g in SPEC["gaits"])
SCALE = SPEC["phase_scale"]
MOVE_DENOMINATOR = 100 * 10 * SPEC["source_tile_pixels"] * SCALE


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
