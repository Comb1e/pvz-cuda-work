"""Optional pygame-ce interface. Draws original vector-style art from public state."""

from __future__ import annotations

import os
from collections import deque
from datetime import datetime
from enum import StrEnum
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from . import Game, LevelSpec, Place, Rules, Status, Wait, WaveSpec
from .art import BG, CREAM, GREEN, LABELS, MUTED, PANEL, YELLOW, Painter
from .art import plant_art as plant_art
from .art import zombie_art as zombie_art
from .config import PLANT_TYPES
from .rendering import BoardRenderer, RenderContext, RenderOptions
from .replay import Playback, Recorder
from .types import Dig


class Screen(StrEnum):
    MENU = "menu"
    PLAYING = "playing"
    PAUSED = "paused"
    ENDED = "ended"


class App(Painter):
    def __init__(
        self,
        level: str | LevelSpec | WaveSpec | None = None,
        seed=None,
        rules: Rules | None = None,
        record_path: Path | None = None,
        replay_path: Path | None = None,
        ui_config: Path | None = None,
    ):
        self.renderer = BoardRenderer(ui_config=ui_config)
        config = self.renderer.cfg
        self.cfg = config
        pygame.display.init()
        self.surface = pygame.display.set_mode(self.renderer.native_size)
        pygame.display.set_caption(config["title"] + " | deterministic daytime defense")
        self.fonts = self.renderer.fonts
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
        metadata = self.playback.metadata if self.playback else {}
        outcome = self.playback.display_outcome if self.playback else obs.status.value
        selected = self.selected if self.mode == Screen.PLAYING and not self.playback else None
        self.renderer.draw(
            obs,
            self.surface,
            context=RenderContext(
                policy_id=metadata.get("policy_id"),
                outcome=outcome,
                termination_reason=metadata.get("termination_reason"),
                message=self.message,
            ),
            options=RenderOptions(
                selected_plant=selected,
                hover_tile=self.tile_at(pygame.mouse.get_pos()),
                legal_actions=self.game.legal_actions() if selected else (),
                inspect=self.inspect,
                show_outcome=False,
                show_status=False,
                effects=tuple(self.effects),
                sun_flash_until=self.sun_flash_until,
            ),
        )
        self.buttons = {
            "card:" + card.plant_type: self.renderer.card_rect(i)
            for i, card in enumerate(obs.cards)
        }
        self.button("shovel", "Shovel [S]", (978, 105, 129, 42), self.selected == "shovel")
        self.button("inspect", "Inspect [I]", (1115, 105, 129, 42), self.inspect)
        self.button(
            "pause", "Resume" if self.mode == Screen.PAUSED else "Pause", (978, 158, 129, 42)
        )
        self.button("speed", f"Speed {self.speed}x", (1115, 158, 129, 42))
        if not self.playback:
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
        external = self.playback.display_outcome if self.playback else None
        if not paused and external in ("truncated", "interrupted"):
            heading = "Replay " + external
        self.text(heading, 640, 276, 30, GREEN if obs.status == Status.WON else CREAM, True)
        subtitle = (
            "Take a breath. Your garden can wait."
            if paused
            else (f"{obs.counts.defeated} defeated  /  {obs.elapsed_seconds:.1f} seconds")
        )
        if not paused and external in ("truncated", "interrupted"):
            reason = self.playback.metadata.get("termination_reason", "External controller stopped")
            subtitle = reason.replace("_", " ")[:48]
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
