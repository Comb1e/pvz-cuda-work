"""Synchronous live demo preview. Simulation steps remain owned by DemoSession."""

from time import perf_counter

from .art import BG, CREAM, GREEN, MUTED, Painter, pygame
from .config import bundled
from .demo import DemoCancelled
from .rendering import BoardRenderer, RenderContext, RenderOptions
from .replay import RecordedOperation, operation_text, validate_speed
from .types import Dig, Place, Status


class LivePreview(Painter):
    def __init__(self, observation, *, speed=1, metadata=None):
        validate_speed(speed)
        if pygame.display.get_surface() is not None:
            raise RuntimeError(
                "live demo needs its own window; another pygame window is already open"
            )
        self.renderer = BoardRenderer()
        self.cfg, self.fonts = self.renderer.cfg, self.renderer.fonts
        pygame.display.init()
        self.surface = pygame.display.set_mode(self.renderer.native_size)
        self.metadata = metadata or {}
        pygame.display.set_caption("Lawn Lab | " + str(self.metadata.get("title", "Live demo")))
        self.observation = observation
        self.speed = speed
        self.speeds = bundled("demo.toml")["speeds"]
        self.paused = False
        self.single_step = False
        self.inspect = False
        self.closed = False
        self.accumulator = 0.0
        self.clock = pygame.time.Clock()
        self.last_draw = 0.0
        self.last_operation = None
        self.pause_rect = pygame.Rect(978, 105, 129, 42)
        self.speed_rect = pygame.Rect(1115, 105, 129, 42)
        self.draw()

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            raise DemoCancelled("live demo window closed")
        pause = event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_ESCAPE)
        speed = False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pause = self.pause_rect.collidepoint(event.pos)
            speed = self.speed_rect.collidepoint(event.pos)
        if pause:
            self.paused = not self.paused
            self.accumulator = 0
        if speed:
            self.speed = self.speeds[(self.speeds.index(self.speed) + 1) % len(self.speeds)]
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_PERIOD and self.paused:
                self.single_step = True
            elif event.key == pygame.K_i:
                self.inspect = not self.inspect

    def before_tick(self):
        interval = 1 / self.observation.tick_rate
        while True:
            for event in pygame.event.get():
                self.handle_event(event)
            if self.paused and self.single_step:
                self.single_step = False
                return
            if not self.paused and self.accumulator >= interval:
                self.accumulator -= interval
                return
            self.draw()
            elapsed = self.clock.tick(self.cfg["fps"]) / 1000
            if not self.paused:
                self.accumulator += elapsed * self.speed

    def after_tick(self, result, action):
        self.observation = result.observation
        if isinstance(action, (Place, Dig)):
            self.last_operation = RecordedOperation(
                result.observation.tick - 1, action, result.action_result
            )
        if (
            perf_counter() - self.last_draw >= 1 / self.cfg["fps"]
            or result.status != Status.RUNNING
        ):
            self.draw()

    def draw(self):
        self.renderer.draw(
            self.observation,
            self.surface,
            context=RenderContext(message=operation_text(self.last_operation)),
            options=RenderOptions(inspect=self.inspect, show_status=False),
        )
        for rect, text in (
            (self.pause_rect, "Resume" if self.paused else "Pause"),
            (self.speed_rect, f"Speed {self.speed:g}x"),
        ):
            self.panel(rect, BG, border=GREEN)
            self.text(text, rect.centerx, rect.y + 10, 15, CREAM, True)
        self.text("LIVE RECORDING", 988, 166, 17, GREEN)
        self.text(
            "Space pause  /  . single tick  /  I inspect  /  Close to save and stop",
            64,
            778,
            13,
            MUTED,
        )
        pygame.display.flip()
        self.last_draw = perf_counter()

    def close(self):
        if not self.closed:
            pygame.display.quit()
            self.closed = True
