"""Optional pygame-ce interface. Draws original vector-style art from public state."""

from __future__ import annotations

import math
import os
import tomllib
from collections import deque
from datetime import datetime
from enum import StrEnum
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from . import Game, LevelSpec, Place, Rules, Status, Wait, WaveSpec
from .config import PLANT_TYPES, bundled
from .replay import Playback, Recorder
from .types import Dig

BG = (20, 39, 36)
PANEL = (30, 54, 47)
CREAM = (244, 239, 216)
MUTED = (157, 180, 158)
GREEN = (155, 212, 119)
YELLOW = (248, 207, 94)
PURPLE = (180, 149, 229)
RED = (227, 117, 101)
INK = (32, 56, 38)
LABELS = {
    "sunflower": "Sunflower",
    "peashooter": "Peashooter",
    "wall_nut": "Wall-nut",
    "cherry_bomb": "Cherry Bomb",
    "potato_mine": "Potato Mine",
    "snow_pea": "Snow Pea",
    "chomper": "Chomper",
    "repeater": "Repeater",
}


class Screen(StrEnum):
    MENU = "menu"
    PLAYING = "playing"
    PAUSED = "paused"
    ENDED = "ended"


def plant_art(surface, kind, x, y, scale=1.0, state="ready", phase=0):
    """Small original illustrations, reusable in cards, the lawn, and menus."""

    def point(px, py):
        return round(x + px * scale), round(y + py * scale)

    def circle(color, px, py, radius, width=0):
        pygame.draw.circle(surface, color, point(px, py), max(1, round(radius * scale)), width)

    def ellipse(color, px, py, w, h, width=0):
        pygame.draw.ellipse(
            surface, color, (*point(px, py), round(w * scale), round(h * scale)), width
        )

    def line(color, points, width=3):
        pygame.draw.lines(
            surface, color, False, [point(*p) for p in points], max(1, round(width * scale))
        )

    def eyes(px, py):
        circle(INK, px - 7, py, 2.3)
        circle(INK, px + 7, py, 2.3)

    ellipse((65, 100, 58), -27, 25, 54, 11)
    if kind == "wall_nut":
        ellipse((111, 72, 40), -25, -33, 50, 69)
        ellipse((190, 139, 79), -23, -34, 46, 65)
        ellipse((208, 160, 99), -16, -28, 25, 51)
        eyes(0, -6)
        line(INK, [(-5, 9), (0, 12), (6, 8)], 2)
        if state == "damaged":
            line((114, 76, 48), [(-9, -29), (-4, -16), (-12, -2), (-7, 8)], 2)
        return
    if kind == "potato_mine":
        ellipse((135, 102, 68), -30, -7, 60, 39)
        ellipse((192, 157, 103), -25, -9, 50, 33)
        eyes(0, 4)
        line(INK, [(0, -9), (0, -24)], 3)
        circle(RED if state == "armed" else (138, 140, 102), 0, -27, 7)
        if state == "armed":
            circle(YELLOW, -1, -29, 2)
        return
    if kind == "cherry_bomb":
        line((83, 128, 62), [(-15, -4), (-7, -35), (11, -27), (17, -5)], 4)
        ellipse((103, 160, 70), 0, -38, 24, 12)
        circle((166, 56, 66), -15, 8, 20)
        circle((226, 77, 84), 14, 10, 23)
        circle((249, 143, 129), 7, 0, 5)
        eyes(14, 8)
        line(INK, [(8, 20), (19, 20)], 2)
        return
    line((67, 133, 67), [(0, 26), (0, -9)], 7)
    ellipse((89, 163, 77), -25, 10, 27, 14)
    ellipse((114, 185, 87), 0, 13, 27, 14)
    if kind == "sunflower":
        for i in range(10):
            angle = i * math.tau / 10 + phase * 0.025
            circle(YELLOW, math.cos(angle) * 24, -18 + math.sin(angle) * 24, 10)
        circle((98, 69, 42), 0, -18, 23)
        circle((167, 112, 53), 0, -18, 19)
        eyes(0, -20)
        line(INK, [(-6, -10), (0, -6), (7, -11)], 2)
    elif kind == "chomper":
        ellipse((100, 71, 136), -29, -39, 59, 53)
        ellipse(PURPLE, -25, -37, 52, 43)
        if state == "digesting":
            line(INK, [(-13, -11), (22, -11)], 3)
        else:
            pygame.draw.polygon(
                surface, INK, [point(-3, -23), point(32, -30), point(25, 0), point(-3, -4)]
            )
            for i in range(3):
                pygame.draw.polygon(
                    surface,
                    CREAM,
                    [point(4 + i * 8, -23), point(10 + i * 8, -25), point(7 + i * 8, -15)],
                )
        circle(INK, -13, -27, 3)
    else:
        color = (129, 201, 206) if kind == "snow_pea" else (127, 186, 86)
        dark = (59, 118, 137) if kind == "snow_pea" else (59, 121, 63)
        if kind == "repeater":
            ellipse(dark, -20, -39, 41, 35)
            ellipse(color, 4, -35, 33, 22)
            ellipse(INK, 28, -34, 10, 19)
        circle(dark, -3, -11, 24)
        circle(color, -5, -14, 22)
        ellipse(color, 6, -23, 33, 24)
        ellipse(dark, 29, -23, 12, 25)
        ellipse(INK, 33, -18, 6, 14)
        circle(INK, -10, -20, 3)
        circle(CREAM, -11, -22, 1.3)
        if kind == "snow_pea":
            for dx, dy in [(-20, -38), (0, -42), (13, -33)]:
                line(CREAM, [(dx - 4, dy), (dx + 4, dy)], 1)
                line(CREAM, [(dx, dy - 4), (dx, dy + 4)], 1)


def zombie_art(surface, kind, x, y, *, tick=0, state="walking", armor=0, slow=False):
    x, y = round(x), round(y)
    sway = round(math.sin(tick * 0.2) * 3) if state not in ("biting", "vaulting") else 0
    if state == "vaulting":
        y -= 16
    skin = (157, 182, 167) if not slow else (142, 199, 216)
    pygame.draw.ellipse(surface, (71, 102, 64), (x - 22, y + 30, 48, 10))
    pygame.draw.line(surface, (68, 80, 85), (x - 8, y + 10), (x - 12 + sway, y + 32), 9)
    pygame.draw.line(surface, (68, 80, 85), (x + 8, y + 10), (x + 12 - sway, y + 32), 9)
    pygame.draw.rect(surface, (115, 96, 117), (x - 16, y - 16, 32, 38), border_radius=6)
    pygame.draw.line(surface, skin, (x - 13, y - 8), (x - 34, y + 2), 7)
    pygame.draw.line(surface, skin, (x + 13, y - 5), (x - 14, y + 8), 6)
    pygame.draw.ellipse(surface, skin, (x - 20, y - 49, 41, 39))
    pygame.draw.circle(surface, CREAM, (x - 11, y - 31), 6)
    pygame.draw.circle(surface, INK, (x - 13, y - 30), 2)
    pygame.draw.circle(surface, CREAM, (x + 5, y - 33), 5)
    pygame.draw.circle(surface, INK, (x + 3, y - 32), 2)
    pygame.draw.line(surface, INK, (x - 14, y - 18), (x + 7, y - 18), 3)
    pygame.draw.rect(surface, CREAM, (x - 8, y - 19, 5, 5))
    if kind == "conehead" and armor:
        pygame.draw.polygon(
            surface, (224, 133, 73), [(x - 24, y - 46), (x + 19, y - 46), (x + 1, y - 84)]
        )
        pygame.draw.line(surface, CREAM, (x - 12, y - 59), (x + 12, y - 59), 5)
    elif kind == "buckethead" and armor:
        pygame.draw.polygon(
            surface,
            (170, 189, 188),
            [(x - 21, y - 43), (x + 23, y - 43), (x + 16, y - 74), (x - 15, y - 74)],
        )
        pygame.draw.line(surface, (111, 139, 140), (x - 25, y - 44), (x + 26, y - 44), 5)
        pygame.draw.line(surface, (212, 221, 207), (x - 9, y - 67), (x - 11, y - 50), 3)
    elif kind == "flag":
        pygame.draw.line(surface, (109, 91, 63), (x + 28, y + 15), (x + 28, y - 77), 3)
        pygame.draw.polygon(surface, PURPLE, [(x + 29, y - 77), (x + 60, y - 67), (x + 29, y - 57)])
    elif kind == "pole_vaulting" and state in ("carrying_pole", "vaulting"):
        pygame.draw.line(surface, (226, 208, 154), (x - 42, y + 22), (x + 52, y - 50), 4)
        pygame.draw.line(surface, RED, (x - 5, y - 56), (x + 17, y - 55), 5)


class App:
    def __init__(
        self,
        level: str | LevelSpec | WaveSpec | None = None,
        seed=None,
        rules: Rules | None = None,
        record_path: Path | None = None,
        replay_path: Path | None = None,
        ui_config: Path | None = None,
    ):
        pygame.display.init()
        pygame.font.init()
        config = bundled("ui.toml")
        if ui_config:
            with open(ui_config, "rb") as stream:
                override = tomllib.load(stream)
            if set(override) - set(config):
                raise ValueError("unknown UI setting")
            config.update(override)
        for key in ("width", "height", "fps", "tile_width", "tile_height"):
            if type(config[key]) is not int or config[key] <= 0:
                raise ValueError(f"{key} must be a positive integer")
        if (
            config["width"] < 1280
            or config["height"] < 820
            or config["board_x"] + 9 * config["tile_width"] > config["sidebar_x"] - 20
            or config["board_y"] + 5 * config["tile_height"] > config["height"] - 70
        ):
            raise ValueError("UI layout requires at least 1280x820 and room for board and sidebar")
        self.cfg = config
        self.surface = pygame.display.set_mode((config["width"], config["height"]))
        pygame.display.set_caption(config["title"] + " | deterministic daytime defense")
        self.fonts = {
            size: pygame.font.SysFont("Segoe UI", size, bold=size >= 24)
            for size in (13, 15, 17, 20, 24, 30, 38, 64)
        }
        self.clock = pygame.time.Clock()
        self.rules = rules or Rules()
        self.game = Game(self.rules)
        self.seed = config["default_seed"] if seed is None else seed
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        self.seed_text = str(self.seed)
        self.level = level or "standard"
        self.mode = Screen.MENU
        self.selected: str | None = None
        self.inspect = False
        self.speed = 1
        self.accumulator = 0.0
        self.pending = deque()
        self.effects: list[tuple[int, int, int, int]] = []
        self.sun_flash_until = 0
        self.record_path = record_path
        self.recorder: Recorder | None = None
        self.saved_tick = -1
        self.playback: Playback | None = None
        self.replay_path = replay_path
        self.message = "Choose a card, then plant on an empty tile."
        self.buttons: dict[str, pygame.Rect] = {}
        self.running = True
        if replay_path:
            self.playback = Playback(replay_path)
            self.game = self.playback.game
            self.rules = self.game.rules
            self.mode = Screen.ENDED if self.playback.done else Screen.PLAYING
            self.message = "REPLAY  /  controls are read-only"
        elif level:
            self.start(level)

    def start(self, level):
        self._autosave()
        self.level = level
        self.game.reset(level, self.seed)
        self.recorder = Recorder(self.game)
        self.saved_tick = -1
        self.mode = Screen.PLAYING
        self.accumulator = 0
        self.pending.clear()
        self.effects.clear()
        self.sun_flash_until = 0
        self.selected = None
        self.message = "Plant sunflowers early. Cover every lane."

    def _autosave(self):
        if self.record_path and self.recorder:
            self.save_recording(self.record_path)

    def save_recording(self, path: Path | None = None):
        if not self.recorder:
            return
        tick = self.game.observe().tick
        if tick == self.saved_tick:
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = path or Path("recordings") / f"{self.game.observe().level}-{stamp}.json"
        if destination.exists():
            destination = destination.with_name(f"{destination.stem}-{stamp}{destination.suffix}")
        self.recorder.save(destination)
        self.saved_tick = tick
        self.message = f"Replay saved: {destination.name}"

    def text(self, text, x, y, size=17, color=CREAM, center=False):
        rendered = self.fonts[size].render(str(text), True, color)
        rect = rendered.get_rect(midtop=(x, y)) if center else rendered.get_rect(topleft=(x, y))
        self.surface.blit(rendered, rect)
        return rect

    def panel(self, rect, color=PANEL, radius=14, border=None):
        pygame.draw.rect(self.surface, color, rect, border_radius=radius)
        if border:
            pygame.draw.rect(self.surface, border, rect, 2, border_radius=radius)

    def button(self, name, label, rect, active=False):
        rect = pygame.Rect(rect)
        self.buttons[name] = rect
        hover = rect.collidepoint(pygame.mouse.get_pos())
        self.panel(
            rect,
            (54, 81, 58) if hover or active else PANEL,
            border=GREEN if active else (72, 94, 71),
        )
        self.text(label, rect.centerx, rect.y + 10, 15, center=True)

    def board_rect(self):
        c = self.cfg
        return pygame.Rect(c["board_x"], c["board_y"], 9 * c["tile_width"], 5 * c["tile_height"])

    def tile_at(self, pos):
        if not self.board_rect().collidepoint(pos):
            return None
        return (
            (pos[1] - self.cfg["board_y"]) // self.cfg["tile_height"],
            (pos[0] - self.cfg["board_x"]) // self.cfg["tile_width"],
        )

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.KEYDOWN:
            if self.mode == Screen.MENU:
                if event.key == pygame.K_BACKSPACE:
                    self.seed_text = self.seed_text[:-1]
                elif event.unicode.isdecimal() and len(self.seed_text) < 10:
                    self.seed_text += event.unicode
                elif event.key == pygame.K_RETURN:
                    self.seed = int(self.seed_text or "0")
                    self.start("standard")
                return
            if event.key in (pygame.K_ESCAPE, pygame.K_SPACE):
                if event.key == pygame.K_ESCAPE and self.selected:
                    self.selected = None
                else:
                    self.toggle_pause()
            elif event.key == pygame.K_i:
                self.inspect = not self.inspect
            elif event.key == pygame.K_PERIOD:
                if self.mode == Screen.PAUSED:
                    self.advance()
            elif event.key == pygame.K_r:
                self.restart()
            elif event.key == pygame.K_F5:
                self.save_recording()
            elif not self.playback and self.mode == Screen.PLAYING:
                if pygame.K_1 <= event.key <= pygame.K_8:
                    self.selected = PLANT_TYPES[event.key - pygame.K_1]
                elif event.key == pygame.K_s:
                    self.selected = "shovel"
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        if event.button == 3:
            self.selected = None
            return
        if event.button != 1:
            return
        for name, rect in self.buttons.items():
            if rect.collidepoint(event.pos):
                self.activate(name)
                return
        if self.mode == Screen.PLAYING and not self.playback and self.selected:
            tile = self.tile_at(event.pos)
            if tile:
                action = Dig(*tile) if self.selected == "shovel" else Place(self.selected, *tile)
                # Queue at most one pending click. Execution validates again on the next tick.
                if not self.pending:
                    self.pending.append(action)

    def activate(self, name):
        if name.startswith("level:"):
            self.seed = int(self.seed_text or "0")
            self.start(name.split(":")[1])
        elif name.startswith("card:") and not self.playback and self.mode == Screen.PLAYING:
            self.selected = name.split(":")[1]
        elif name == "shovel" and not self.playback:
            self.selected = "shovel"
        elif name == "pause":
            self.toggle_pause()
        elif name == "speed":
            self.speed = {1: 2, 2: 4, 4: 1}[self.speed]
        elif name == "inspect":
            self.inspect = not self.inspect
        elif name == "step" and self.mode == Screen.PAUSED:
            self.advance()
        elif name == "restart":
            self.restart()
        elif name == "save":
            self.save_recording()
        elif name == "menu":
            self._autosave()
            self.playback = None
            self.recorder = None
            self.mode = Screen.MENU
            self.pending.clear()

    def restart(self):
        if self.playback:
            self.playback = Playback(self.replay_path)
            self.game = self.playback.game
            self.mode = Screen.ENDED if self.playback.done else Screen.PLAYING
            self.accumulator = 0
        else:
            self.start(self.level)

    def toggle_pause(self):
        if self.mode == Screen.PLAYING:
            self.mode = Screen.PAUSED
            self.pending.clear()
        elif self.mode == Screen.PAUSED:
            self.mode = Screen.PLAYING
        self.accumulator = 0

    def advance(self):
        if self.game.observe().status != Status.RUNNING:
            self.mode = Screen.ENDED
            return
        if self.playback:
            if self.playback.done:
                self.mode = Screen.ENDED
                return
            result = self.playback.step()
            if self.playback.done:
                self.mode = Screen.ENDED
                self.message = "Replay verified. Every recorded state matched."
        else:
            action = self.pending.popleft() if self.pending else Wait()
            result = self.recorder.step(action)
            if not result.action_result.accepted:
                self.message = result.action_result.reason.replace("_", " ").capitalize() + "."
            elif isinstance(action, Place):
                self.message = f"{LABELS[action.plant_type]} planted."
            elif isinstance(action, Dig):
                self.message = "Plant removed. No sun refund."
        if result.status != Status.RUNNING:
            self.mode = Screen.ENDED
            self.pending.clear()
            self._autosave()
        tick = result.observation.tick
        self.effects = [effect for effect in self.effects if effect[0] > tick]
        for event in result.events:
            if event.kind == "PlantExploded":
                self.effects.append(
                    (tick + 12, event.get("row"), event.get("col"), event.get("radius"))
                )
            elif event.kind == "SunProduced" and event.get("amount"):
                self.sun_flash_until = tick + 8

    def draw_menu(self):
        self.text("LAWN LAB", 78, 70, 64)
        self.text("A little garden. A very determined horde.", 82, 153, 24, MUTED)
        self.text("DAYTIME DEFENSE", 84, 226, 15, GREEN)
        self.text("Grow an economy. Protect five lanes.", 82, 263, 30)
        self.text("Sun collects automatically. Every zombie counts.", 84, 315, 20, MUTED)
        for i, (level, summary, count) in enumerate(
            (
                ("easy", "Room to grow", "5 waves / 15 zombies"),
                ("standard", "The whole garden", "10 waves / 40 zombies"),
                ("hard", "A crowded afternoon", "15 waves / 75 zombies"),
            )
        ):
            x = 84 + i * 380
            self.panel((x, 415, 350, 204))
            self.text(level.title(), x + 22, 435, 30)
            self.text(summary, x + 22, 481, 17, MUTED)
            self.text(count, x + 22, 508, 15, MUTED)
            self.button("level:" + level, "Start " + level, (x + 22, 550, 306, 46), i == 1)
        self.text("SCENARIO SEED", 86, 661, 13, MUTED)
        self.panel((84, 689, 194, 47), border=(67, 95, 75))
        self.text(self.seed_text or "0", 103, 697, 24, YELLOW)
        self.text("Type digits to edit / Backspace to erase", 300, 702, 15, MUTED)
        self.text(
            "1–8 select   ·   Click to plant   ·   Space to pause   ·   I to inspect",
            84,
            774,
            15,
            MUTED,
        )
        for i, kind in enumerate(("sunflower", "peashooter", "wall_nut", "chomper")):
            plant_art(self.surface, kind, 838 + (i % 2) * 178, 153 + (i // 2) * 133, 1.25)

    def draw(self):
        self.surface.fill(BG)
        self.buttons = {}
        if self.mode == Screen.MENU:
            self.draw_menu()
            return
        obs = self.game.observe()
        self.text("LAWN LAB", 34, 22, 30)
        self.text("DAYTIME DEFENSE", 236, 34, 13, GREEN)
        title = "REPLAY" if self.playback else obs.level.upper()
        self.text(f"{title}   /   {obs.elapsed_seconds:05.1f}s", 694, 32, 17, MUTED)
        self.panel((978, 20, 266, 70), (59, 63, 39))
        pygame.draw.circle(
            self.surface, YELLOW, (1007, 54), 16 if obs.tick < self.sun_flash_until else 13
        )
        self.text(obs.sun, 1034, 23, 38, YELLOW)
        self.text("AUTO SUN", 1137, 47, 13, MUTED)
        for i, card in enumerate(obs.cards):
            x = 34 + i * 114
            rect = pygame.Rect(x, 84, 105, 116)
            selected = self.selected == card.plant_type
            unavailable = card.cooldown_ticks or obs.sun < card.cost
            self.panel(
                rect,
                (49, 74, 52) if selected else PANEL,
                border=GREEN if selected else (59, 81, 64),
            )
            self.buttons["card:" + card.plant_type] = rect
            self.text(i + 1, x + 9, 89, 13, MUTED)
            plant_art(self.surface, card.plant_type, x + 54, 132, 0.52)
            self.text(
                LABELS[card.plant_type], x + 52, 161, 13, MUTED if unavailable else CREAM, True
            )
            self.text(f"{card.cost}", x + 52, 179, 13, YELLOW, True)
            if card.cooldown_ticks:
                width = round(89 * (1 - card.cooldown_ticks / card.recharge_ticks))
                pygame.draw.rect(self.surface, (64, 85, 64), (x + 8, 152, 89, 4))
                pygame.draw.rect(self.surface, GREEN, (x + 8, 152, width, 4))
                self.text(f"{card.cooldown_ticks / 20:.1f}s", x + 56, 90, 13, MUTED)
        self.button("shovel", "Shovel [S]", (978, 105, 129, 42), self.selected == "shovel")
        self.button("inspect", "Inspect [I]", (1115, 105, 129, 42), self.inspect)
        self.button(
            "pause", "Resume" if self.mode == Screen.PAUSED else "Pause", (978, 158, 129, 42)
        )
        self.button("speed", f"Speed {self.speed}x", (1115, 158, 129, 42))
        self._draw_lawn(obs)
        self._draw_sidebar(obs)
        self.text(self.message[:108], 64, 729, 17, CREAM)
        self.text(
            "1–8 select   ·   Click plant   ·   Right-click cancel   ·   Space pause"
            "   ·   . single tick   ·   R restart   ·   F5 save replay",
            64,
            778,
            13,
            MUTED,
        )
        if self.mode in (Screen.PAUSED, Screen.ENDED):
            self._draw_modal(obs)

    def _draw_lawn(self, obs):
        c = self.cfg
        board = self.board_rect()
        self.panel(board.inflate(14, 14), (94, 129, 76), radius=13)
        hover = self.tile_at(pygame.mouse.get_pos())
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
                if self.selected and not self.playback and self.mode == Screen.PLAYING:
                    action = (
                        Dig(row, col)
                        if self.selected == "shovel"
                        else Place(self.selected, row, col)
                    )
                    legal = self.game.validate_action(action).accepted
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
            plant_art(self.surface, p.plant_type, x, y, 0.85, state, obs.tick / 20)
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
        self.text("ZOMBIES REMAINING", x + 20, 246, 13, MUTED)
        self.text(obs.counts.remaining, x + 19, 271, 64)
        self.text(f"{obs.counts.alive} on lawn", x + 20, 361, 17, GREEN)
        self.text(f"{obs.counts.not_yet_spawned} upcoming", x + 138, 361, 17, MUTED)
        pygame.draw.line(self.surface, (65, 87, 66), (x + 20, 404), (x + 244, 404))
        self.text(f"WAVE {obs.wave} / {obs.total_waves}", x + 20, 424, 15, CREAM)
        self.text(f"{obs.counts.defeated} defeated", x + 20, 455, 15, MUTED)
        self.text("MOWERS", x + 20, 504, 13, MUTED)
        for i, m in enumerate(obs.mowers):
            color = GREEN if m.state == "ready" else YELLOW if m.state == "moving" else (61, 81, 63)
            pygame.draw.circle(self.surface, color, (x + 33 + i * 46, 541), 10)
            self.text(chr(65 + i), x + 33 + i * 46, 559, 13, MUTED, True)
        if self.inspect:
            tile = self.tile_at(pygame.mouse.get_pos())
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

    def _draw_modal(self, obs):
        veil = pygame.Surface(self.surface.get_size(), pygame.SRCALPHA)
        veil.fill((9, 23, 20, 185))
        self.surface.blit(veil, (0, 0))
        self.buttons = {}  # No click-through to the board or toolbar beneath the modal.
        self.panel((395, 247, 490, 330), BG, border=(87, 119, 84))
        paused = self.mode == Screen.PAUSED
        heading = (
            "Garden paused"
            if paused
            else "Lawn defended!"
            if obs.status == Status.WON
            else ("The horde got through" if obs.status == Status.LOST else "Replay complete")
        )
        self.text(heading, 640, 276, 30, GREEN if obs.status == Status.WON else CREAM, True)
        subtitle = (
            "Take a breath. Your garden can wait."
            if paused
            else (f"{obs.counts.defeated} defeated  /  {obs.elapsed_seconds:.1f} seconds")
        )
        self.text(subtitle, 640, 330, 17, MUTED, True)
        self.button(
            "pause" if paused else "restart",
            "Resume" if paused else "Play again",
            (430, 378, 420, 45),
            True,
        )
        self.button(
            "step" if paused else "save",
            "Advance one tick [.]" if paused else "Save replay",
            (430, 434, 202, 44),
        )
        self.button("restart", "Restart [R]", (645, 434, 205, 44))
        self.button("menu", "Choose a level", (430, 490, 420, 44))

    def run(self):
        try:
            while self.running:
                elapsed = self.clock.tick(self.cfg["fps"]) / 1000
                for event in pygame.event.get():
                    self.handle_event(event)
                if self.mode == Screen.PLAYING:
                    self.accumulator += elapsed * self.speed
                    # Limit work per frame while retaining the backlog; never discard ticks.
                    count = 0
                    while self.accumulator >= 1 / 20 and count < 80 and self.mode == Screen.PLAYING:
                        self.advance()
                        self.accumulator -= 1 / 20
                        count += 1
                self.draw()
                pygame.display.flip()
        finally:
            self._autosave()
            pygame.quit()
