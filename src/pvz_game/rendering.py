"""Render a public Observation to a Surface or packed RGB bytes, without a window."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .art import (
    BG,
    CREAM,
    GREEN,
    INK,
    LABELS,
    MUTED,
    PANEL,
    PURPLE,
    RED,
    YELLOW,
    Painter,
    plant_art,
    pygame,
    zombie_art,
)
from .config import bundled
from .replay import presentation_outcome
from .types import API_VERSION, Action, Dig, Observation, Place


def load_ui_config(path: str | Path | None = None) -> dict:
    config = bundled("ui.toml")
    if path:
        with open(path, "rb") as stream:
            override = tomllib.load(stream)
        if set(override) - set(config):
            raise ValueError("unknown UI setting")
        config.update(override)
    for key in ("width", "height", "fps", "tile_width", "tile_height"):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    for key in ("board_x", "board_y", "sidebar_x", "default_seed"):
        if type(config[key]) is not int or config[key] < 0:
            raise ValueError(f"{key} must be a nonnegative integer")
    if (
        config["width"] < 1280
        or config["height"] < 820
        or config["board_x"] + 9 * config["tile_width"] > config["sidebar_x"] - 20
        or config["board_y"] + 5 * config["tile_height"] > config["height"] - 70
        or config["sidebar_x"] + 264 > config["width"]
    ):
        raise ValueError("UI layout requires at least 1280x820 and room for board and sidebar")
    return config


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Optional external presentation labels. Never part of a policy observation."""

    policy_id: str | None = None
    outcome: str | None = None
    termination_reason: str | None = None
    message: str = ""

    def __post_init__(self):
        for key in ("policy_id", "outcome", "termination_reason"):
            value = getattr(self, key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be a string or None")
        if not isinstance(self.message, str):
            raise ValueError("message must be a string")
        if self.outcome not in (None, "running", "won", "lost", "truncated", "interrupted"):
            raise ValueError("unknown presentation outcome")


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Optional interactive overlays, supplied explicitly instead of reading input devices."""

    selected_plant: str | None = None
    hover_tile: tuple[int, int] | None = None
    legal_actions: tuple[Action, ...] = ()
    inspect: bool = False
    show_outcome: bool = True
    show_status: bool = True
    effects: tuple[tuple[int, int, int, int], ...] = ()
    sun_flash_until: int = 0


@dataclass(frozen=True, slots=True)
class RGBFrame:
    """Top-to-bottom, row-major RGB24 pixels: exactly width * height * 3 bytes."""

    width: int
    height: int
    data: bytes


class BoardRenderer:
    """Reusable board/HUD renderer; initializes fonts only and never creates a display.

    ``render`` returns a fresh Surface; ``rgb_frame`` returns independent packed bytes.
    Optional output sizing preserves aspect ratio with background-colored letterboxing.
    """

    def __init__(self, *, size: tuple[int, int] | None = None, ui_config: str | Path | None = None):
        self.cfg = load_ui_config(ui_config)
        self.native_size = (self.cfg["width"], self.cfg["height"])
        self.size = self.native_size if size is None else size
        if (
            not isinstance(self.size, tuple)
            or len(self.size) != 2
            or any(type(n) is not int or n <= 0 for n in self.size)
        ):
            raise ValueError("size must be a pair of positive integers")
        self._fonts = None

    @property
    def fonts(self):
        if not pygame.font.get_init():
            pygame.font.init()
            self._fonts = None
        if self._fonts is None:
            self._fonts = {
                size: pygame.font.SysFont("Segoe UI", size, bold=size >= 24)
                for size in (13, 15, 17, 20, 24, 30, 38, 64)
            }
        return self._fonts

    @staticmethod
    def card_rect(index: int):
        return pygame.Rect(34 + index * 114, 84, 105, 116)

    def draw(
        self,
        observation: Observation,
        surface,
        *,
        context: RenderContext | None = None,
        options: RenderOptions | None = None,
    ):
        """Draw into a caller-owned native-size surface without touching its display."""
        if not isinstance(observation, Observation) or observation.api_version != API_VERSION:
            raise ValueError("renderer requires a compatible public Observation")
        if surface.get_size() != self.native_size:
            raise ValueError("draw requires a native-size surface; use render for scaled output")
        if context is not None and not isinstance(context, RenderContext):
            raise TypeError("context must be RenderContext")
        if options is not None and not isinstance(options, RenderOptions):
            raise TypeError("options must be RenderOptions")
        canvas = _BoardCanvas(surface, self.cfg, self.fonts, options or RenderOptions())
        clip = surface.get_clip()
        try:
            surface.set_clip(None)
            canvas.draw(observation, context or RenderContext())
        finally:
            surface.set_clip(clip)

    def render(
        self,
        observation: Observation,
        *,
        context: RenderContext | None = None,
        options: RenderOptions | None = None,
    ):
        surface = pygame.Surface(self.native_size, depth=32)
        self.draw(observation, surface, context=context, options=options)
        if self.size == self.native_size:
            return surface
        scale = min(self.size[0] / self.native_size[0], self.size[1] / self.native_size[1])
        scaled = pygame.transform.smoothscale(
            surface, tuple(max(1, round(n * scale)) for n in self.native_size)
        )
        frame = pygame.Surface(self.size, depth=32)
        frame.fill(BG)
        frame.blit(scaled, scaled.get_rect(center=frame.get_rect().center))
        return frame

    def rgb_frame(
        self,
        observation: Observation,
        *,
        context: RenderContext | None = None,
        options: RenderOptions | None = None,
    ) -> RGBFrame:
        surface = self.render(observation, context=context, options=options)
        return RGBFrame(*surface.get_size(), pygame.image.tobytes(surface, "RGB"))


class _BoardCanvas(Painter):
    def __init__(self, surface, config, fonts, options):
        self.surface, self.cfg, self.fonts = surface, config, fonts
        self.options = options
        self.selected = options.selected_plant
        self.hover_tile = options.hover_tile
        self.legal_actions = frozenset(options.legal_actions)
        self.inspect = options.inspect
        self.effects = options.effects

    def draw(self, obs, context):
        self.surface.fill(BG)
        self.text("LAWN LAB", 34, 22, 30)
        self.text("DAYTIME DEFENSE", 236, 34, 13, GREEN)
        self.text(
            f"{obs.level.upper()[:24]}   /   {obs.elapsed_seconds:05.1f}s", 694, 32, 17, MUTED
        )
        self.panel((978, 20, 266, 70), (59, 63, 39))
        pygame.draw.circle(
            self.surface, YELLOW, (1007, 54), 16 if obs.tick < self.options.sun_flash_until else 13
        )
        self.text(obs.sun, 1034, 23, 38, YELLOW)
        self.text("AUTO SUN", 1137, 47, 13, MUTED)
        for i, card in enumerate(obs.cards):
            rect = BoardRenderer.card_rect(i)
            x = rect.x
            selected = self.selected == card.plant_type
            unavailable = card.cooldown_ticks or obs.sun < card.cost
            self.panel(
                rect,
                (49, 74, 52) if selected else PANEL,
                border=GREEN if selected else (59, 81, 64),
            )
            self.text(i + 1, x + 9, 89, 13, MUTED)
            plant_art(self.surface, card.plant_type, x + 54, 132, 0.52)
            self.text(
                LABELS[card.plant_type], x + 52, 161, 13, MUTED if unavailable else CREAM, True
            )
            self.text(card.cost, x + 52, 179, 13, YELLOW, True)
            if card.cooldown_ticks:
                width = round(89 * (1 - card.cooldown_ticks / card.recharge_ticks))
                pygame.draw.rect(self.surface, (64, 85, 64), (x + 8, 152, 89, 4))
                pygame.draw.rect(self.surface, GREEN, (x + 8, 152, width, 4))
                self.text(f"{card.cooldown_ticks / obs.tick_rate:.1f}s", x + 56, 90, 13, MUTED)
        outcome = presentation_outcome(obs.status, context.outcome)
        if self.options.show_status:
            self.panel((978, 105, 266, 95))
            self.text(outcome.upper(), 998, 117, 20, GREEN if outcome == "won" else CREAM)
            self.text((context.policy_id or "PUBLIC GAME STATE")[:28], 998, 158, 13, MUTED)
        self._draw_lawn(obs)
        self._draw_sidebar(obs)
        self.text(context.message[:108], 64, 729, 17, CREAM)
        if context.policy_id:
            self.text("Policy: " + context.policy_id[:100], 64, 778, 13, MUTED)
        if self.options.show_outcome and outcome != "running":
            self.panel((430, 380, 420, 105), BG, border=GREEN if outcome == "won" else YELLOW)
            self.text(outcome.upper(), 640, 392, 30, CREAM, True)
            reason = context.termination_reason if outcome in ("truncated", "interrupted") else None
            self.text(
                (reason or f"{obs.counts.defeated} defeated").replace("_", " ")[:52],
                640,
                442,
                15,
                MUTED,
                True,
            )

    def _draw_lawn(self, obs):
        c = self.cfg
        board = self.board_rect()
        self.panel(board.inflate(14, 14), (94, 129, 76), radius=13)
        hover = self.hover_tile
        for row in range(5):
            for col in range(9):
                rect = pygame.Rect(
                    board.x + col * c["tile_width"],
                    board.y + row * c["tile_height"],
                    c["tile_width"],
                    c["tile_height"],
                )
                color = (167, 195, 133) if (row + col) % 2 else (180, 204, 145)
                pygame.draw.rect(self.surface, color, rect)
                # Small, deterministic grass marks make the board readable without assets.
                for dx, dy in ((16, 72), (72, 22)):
                    pygame.draw.line(
                        self.surface,
                        (145, 177, 112),
                        (rect.x + dx, rect.y + dy),
                        (rect.x + dx + 2, rect.y + dy - 4),
                        1,
                    )
                if col == 0:
                    self.text(chr(65 + row), rect.x + 6, rect.y + 5, 13, (93, 130, 77))
                if self.selected:
                    action = (
                        Dig(row, col)
                        if self.selected == "shovel"
                        else Place(self.selected, row, col)
                    )
                    legal = action in self.legal_actions
                    if legal:
                        pygame.draw.rect(self.surface, (210, 231, 159), rect.inflate(-8, -8), 2, 7)
                    if hover == (row, col):
                        pygame.draw.rect(
                            self.surface, CREAM if legal else RED, rect.inflate(-4, -4), 3, 7
                        )
        for col in range(9):
            self.text(
                col + 1,
                board.x + col * c["tile_width"] + c["tile_width"] // 2,
                board.y - 23,
                13,
                MUTED,
                True,
            )
        previous_clip = self.surface.get_clip()
        self.surface.set_clip(pygame.Rect(0, board.y - 14, board.right + 32, board.height + 28))
        for mower in obs.mowers:
            if mower.state == "spent":
                continue
            x = board.x + mower.x / obs.units_per_tile * c["tile_width"] - 25
            y = board.y + mower.row * c["tile_height"] + 58
            pygame.draw.rect(self.surface, (211, 99, 81), (x - 19, y - 13, 39, 23), border_radius=5)
            pygame.draw.circle(self.surface, INK, (round(x - 10), round(y + 10)), 7)
            pygame.draw.circle(self.surface, INK, (round(x + 11), round(y + 10)), 7)
            pygame.draw.line(self.surface, INK, (x - 11, y - 11), (x - 20, y - 28), 3)
        for p in obs.plants:
            x = board.x + (p.col + 0.5) * c["tile_width"]
            y = board.y + (p.row + 0.5) * c["tile_height"] + 5
            state = (
                "damaged"
                if p.plant_type == "wall_nut" and p.health < p.max_health * 0.65
                else p.state
            )
            plant_art(self.surface, p.plant_type, x, y, 0.85, state, obs.elapsed_seconds)
            if self.inspect or p.health < p.max_health:
                pygame.draw.rect(self.surface, (90, 107, 65), (x - 24, y + 32, 48, 4))
                pygame.draw.rect(
                    self.surface, (54, 124, 66), (x - 24, y + 32, 48 * p.health / p.max_health, 4)
                )
        for z in sorted(obs.zombies, key=lambda z: (z.row, z.x, z.id)):
            x = board.x + z.x / obs.units_per_tile * c["tile_width"]
            y = board.y + (z.row + 0.5) * c["tile_height"] + 11
            zombie_art(
                self.surface,
                z.zombie_type,
                x,
                y,
                tick=obs.tick + z.id,
                state=z.state,
                armor=z.armor,
                slow=z.slow_ticks > 0,
            )
            if self.inspect:
                self.text(f"{z.health}+{z.armor}", x, y + 34, 13, INK, True)
        for p in obs.projectiles:
            x = round(board.x + p.x / obs.units_per_tile * c["tile_width"])
            y = round(board.y + (p.row + 0.5) * c["tile_height"] - 8)
            pygame.draw.circle(self.surface, (75, 122, 58), (x, y), 7)
            pygame.draw.circle(
                self.surface, (174, 232, 241) if p.icy else (204, 226, 116), (x - 1, y - 1), 5
            )
        for until, row, col, radius in self.effects:
            x = round(board.x + (col + 0.5) * c["tile_width"])
            y = round(board.y + (row + 0.5) * c["tile_height"])
            size = round((1 - (until - obs.tick) / 12) * (radius + 1) * 60) + 15
            pygame.draw.circle(self.surface, YELLOW, (x, y), size, 4)
        self.surface.set_clip(previous_clip)

    def _draw_sidebar(self, obs):
        x = self.cfg["sidebar_x"]
        self.panel((x, 226, 264, 480))
        self.text("ZOMBIES DEFEATED / TOTAL", x + 20, 246, 13, MUTED)
        progress = f"{obs.counts.defeated}/{obs.counts.initial_total}"
        size = next(
            (
                size
                for size in sorted(self.fonts, reverse=True)
                if self.fonts[size].size(progress)[0] <= 224
            ),
            13,
        )
        self.text(progress, x + 19, 271, size)
        self.text(f"{obs.counts.alive} on lawn", x + 20, 361, 17, GREEN)
        self.text(f"{obs.counts.not_yet_spawned} upcoming", x + 138, 361, 17, MUTED)
        pygame.draw.line(self.surface, (65, 87, 66), (x + 20, 404), (x + 244, 404))
        self.text(f"WAVE {obs.wave} / {obs.total_waves}", x + 20, 424, 15, CREAM)
        self.text(f"{obs.counts.remaining} remaining", x + 20, 455, 15, MUTED)
        self.text("MOWERS", x + 20, 504, 13, MUTED)
        for i, m in enumerate(obs.mowers):
            color = GREEN if m.state == "ready" else YELLOW if m.state == "moving" else (61, 81, 63)
            pygame.draw.circle(self.surface, color, (x + 33 + i * 46, 541), 10)
            self.text(chr(65 + i), x + 33 + i * 46, 559, 13, MUTED, True)
        if self.inspect:
            tile = self.hover_tile
            plant = next((p for p in obs.plants if tile == (p.row, p.col)), None)
            zombie = next(
                (z for z in obs.zombies if tile == (z.row, z.x // obs.units_per_tile)), None
            )
            if zombie:
                self.text(zombie.zombie_type.replace("_", " ").title(), x + 20, 601, 17, PURPLE)
                self.text(f"HP {zombie.health}  Armor {zombie.armor}", x + 20, 630, 15, CREAM)
                self.text(
                    f"{zombie.state} / x {zombie.x / obs.units_per_tile:.2f}",
                    x + 20,
                    655,
                    13,
                    MUTED,
                )
                self.text(
                    f"Slow {zombie.slow_ticks}t / timer {zombie.timer_ticks}t",
                    x + 20,
                    677,
                    13,
                    MUTED,
                )
            elif plant:
                self.text(LABELS[plant.plant_type], x + 20, 601, 17, PURPLE)
                self.text(f"HP {plant.health} / {plant.max_health}", x + 20, 630, 15)
                self.text(f"{plant.state} / {plant.timer_ticks} ticks", x + 20, 658, 13, MUTED)
            else:
                self.text("Hover a unit to inspect", x + 20, 614, 15, MUTED)
                self.text(f"TICK {obs.tick}", x + 20, 650, 13, MUTED)
        else:
            self.text("Sun is collected for you.", x + 20, 614, 15, MUTED)
            self.text("Keep a reserve for surprises.", x + 20, 642, 15, MUTED)
