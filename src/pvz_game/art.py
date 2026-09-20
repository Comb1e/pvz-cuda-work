"""Original drawing primitives shared by interactive and offscreen presentation."""

from __future__ import annotations

import math
import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from .config import bundled

_THEME = bundled("theme.toml")
BG = tuple(_THEME["colors"]["bg"])
PANEL = tuple(_THEME["colors"]["panel"])
CREAM = tuple(_THEME["colors"]["cream"])
MUTED = tuple(_THEME["colors"]["muted"])
GREEN = tuple(_THEME["colors"]["green"])
YELLOW = tuple(_THEME["colors"]["yellow"])
PURPLE = tuple(_THEME["colors"]["purple"])
RED = tuple(_THEME["colors"]["red"])
INK = tuple(_THEME["colors"]["ink"])
LABELS = _THEME["labels"]


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


class Painter:
    """Surface-only layout helpers; the owner supplies cfg, surface, and fonts."""

    def text(self, text, x, y, size=17, color=CREAM, center=False):
        rendered = self.fonts[size].render(str(text), True, color)
        rect = rendered.get_rect(midtop=(x, y)) if center else rendered.get_rect(topleft=(x, y))
        self.surface.blit(rendered, rect)
        return rect

    def panel(self, rect, color=PANEL, radius=14, border=None):
        pygame.draw.rect(self.surface, color, rect, border_radius=radius)
        if border:
            pygame.draw.rect(self.surface, border, rect, 2, border_radius=radius)

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
