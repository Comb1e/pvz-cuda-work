import json
import os
import subprocess
import sys
from dataclasses import replace

import pytest

pygame = pytest.importorskip("pygame")

from pvz_game import Game, Place, Status  # noqa: E402
from pvz_game.rendering import BoardRenderer, RenderContext, RenderOptions  # noqa: E402
from pvz_game.replay import Recorder  # noqa: E402


def test_offscreen_renderer_never_initializes_display_or_reads_input():
    program = """
import os
os.environ['SDL_VIDEODRIVER'] = 'invalid-driver-no-display-allowed'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame
from pvz_game import Game
from pvz_game.rendering import BoardRenderer
assert not pygame.display.get_init()
def forbidden(*args, **kwargs):
    raise AssertionError('offscreen presentation touched display or input')
pygame.display.init = forbidden
pygame.display.set_mode = forbidden
pygame.event.get = forbidden
pygame.mouse.get_pos = forbidden
game = Game()
observation = game.reset()
before = game.state_hash()
renderer = BoardRenderer(size=(1000, 600))
frame = renderer.rgb_frame(observation)
assert (frame.width, frame.height) == (1000, 600)
assert len(frame.data) == 1000 * 600 * 3
assert not pygame.display.get_init()
assert pygame.display.get_surface() is None
assert before == game.state_hash()
print('offscreen verified')
"""
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "offscreen verified" in result.stdout


def test_surface_and_rgb_are_independent_repeatable_and_same_pixels():
    game = Game()
    game.reset()
    game.step(Place("sunflower", 2, 0), ticks=200)
    observation = game.observe()
    before = game.state_hash()
    renderer = BoardRenderer()
    surface = renderer.render(observation)
    pixels = pygame.image.tobytes(surface, "RGB")
    assert renderer.rgb_frame(observation).data == pixels
    renderer.render(replace(observation, sun=200))
    assert pygame.image.tobytes(surface, "RGB") == pixels
    assert renderer.rgb_frame(observation).data == pixels
    # Verify RGB24 layout at a particular pixel independently of surfarray/NumPy.
    x, y = 1007, 54  # Sun icon center.
    index = (y * surface.get_width() + x) * 3
    assert tuple(pixels[index : index + 3]) == tuple(surface.get_at((x, y)))[:3]
    assert game.state_hash() == before


def test_renderer_draws_into_existing_surface_and_restores_clip():
    game = Game()
    obs = game.reset()
    renderer = BoardRenderer()
    expected = renderer.rgb_frame(obs).data
    surface = pygame.Surface(renderer.native_size)
    surface.set_clip((3, 4, 20, 30))
    clip = surface.get_clip()
    renderer.draw(obs, surface)
    assert surface.get_clip() == clip
    assert pygame.image.tobytes(surface, "RGB") == expected


def test_external_context_changes_hud_only_and_is_not_retained():
    game = Game()
    observation = game.reset()
    before = game.state_hash()
    renderer = BoardRenderer()
    plain = renderer.render(observation)
    context = RenderContext(
        policy_id="shared-checkpoint",
        outcome="truncated",
        termination_reason="time limit",
        message="Evaluation finished",
    )
    labeled = renderer.render(observation, context=context)
    assert pygame.image.tobytes(plain, "RGB") != pygame.image.tobytes(labeled, "RGB")
    # Annotation footer/badge/outcome banner change; the top-left lawn tile does not.
    tile = pygame.Rect(64, 226, 98, 96)
    assert pygame.image.tobytes(plain.subsurface(tile), "RGB") == pygame.image.tobytes(
        labeled.subsurface(tile), "RGB"
    )
    assert renderer.rgb_frame(observation).data == pygame.image.tobytes(plain, "RGB")
    assert observation.status == Status.RUNNING
    assert before == game.state_hash()


@pytest.mark.parametrize("size", [(1000, 600), (640, 410), (256, 256), (1, 1)])
def test_scaled_frame_dimensions_and_rgb_length(size):
    obs = Game().reset()
    renderer = BoardRenderer(size=size)
    frame = renderer.rgb_frame(obs)
    assert (frame.width, frame.height) == size
    assert len(frame.data) == size[0] * size[1] * 3


@pytest.mark.parametrize("size", [(0, 600), (-1, 1), (True, 4), (2.5, 6), (1,), "1000x600"])
def test_invalid_frame_size_rejected(size):
    with pytest.raises(ValueError):
        BoardRenderer(size=size)


def test_annotations_cannot_fabricate_a_game_victory():
    obs = Game().reset()
    renderer = BoardRenderer()
    plain = renderer.rgb_frame(obs)
    fake_win = renderer.rgb_frame(obs, context=RenderContext(outcome="won"))
    assert plain == fake_win


def test_render_options_use_explicit_legal_actions():
    game = Game()
    obs = game.reset()
    renderer = BoardRenderer()
    plain = renderer.rgb_frame(obs)
    options = RenderOptions(
        selected_plant="sunflower",
        hover_tile=(2, 0),
        legal_actions=game.legal_actions(),
        inspect=True,
    )
    highlighted = renderer.rgb_frame(obs, options=options)
    assert highlighted != plain
    assert renderer.rgb_frame(obs) == plain


def test_existing_display_is_preserved():
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.display.init()
    surface = pygame.display.set_mode((240, 120))
    try:
        surface.fill((10, 20, 30))
        before = pygame.image.tobytes(surface, "RGB")
        renderer = BoardRenderer()
        renderer.rgb_frame(Game().reset())
        assert pygame.display.get_surface() is surface
        assert pygame.image.tobytes(surface, "RGB") == before
    finally:
        pygame.display.quit()


def test_offscreen_cli_exports_truncated_final_frame(tmp_path):
    game = Game()
    game.reset()
    recorder = Recorder(
        game,
        metadata={
            "policy_id": "shared",
            "outcome": "truncated",
            "termination_reason": "time_limit",
        },
    )
    recorder.step(ticks=4)
    path, image = tmp_path / "replay.json", tmp_path / "frame.png"
    recorder.save(path)
    environment = {
        **os.environ,
        "SDL_VIDEODRIVER": "invalid-driver-no-display-allowed",
        "PYGAME_HIDE_SUPPORT_PROMPT": "1",
    }
    result = subprocess.run(
        [sys.executable, "-m", "pvz_game", "replay", str(path), "--frame", str(image)],
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "running" and summary["outcome"] == "truncated"
    assert image.read_bytes().startswith(b"\x89PNG")
    assert pygame.image.load(image).get_size() == (1280, 820)


def test_renderer_and_legacy_art_imports_share_implementation():
    from pvz_game import art, ui

    assert ui.plant_art is art.plant_art
    assert ui.zombie_art is art.zombie_art
