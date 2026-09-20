import gzip
import json
import subprocess
import sys

import pytest

from pvz_game import Dig, Game, LevelSpec, Place, Spawn, Wait
from pvz_game.cli import main
from pvz_game.demo import DemoSession, ScheduledAction, generate_demo, load_demo_script
from pvz_game.replay import Playback, Recorder, read_recording


def test_compressed_recording_is_deterministic_and_json_compatible(tmp_path):
    game = Game()
    game.reset()
    recorder = Recorder(game)
    recorder.step(Place("sunflower", 2, 0), ticks=1000)
    paths = [tmp_path / name for name in ("a.pvzdemo", "b.pvzdemo", "a.json")]
    for path in paths:
        recorder.save(path)
        assert Playback(path).verify().state_hash() == game.state_hash()
    a, b, plain = (p.read_bytes() for p in paths)
    assert a == b
    assert a[4:8] == b"\0" * 4
    assert gzip.decompress(a) == plain
    assert len(a) < len(plain) / 2


@pytest.mark.parametrize("payload", [b"\x1f\x8b", b'{"initial":', b"[]", b"\xff"])
def test_incomplete_or_invalid_files_rejected(tmp_path, payload):
    path = tmp_path / "bad.pvzdemo"
    path.write_bytes(payload)
    with pytest.raises((ValueError, OSError)):
        Playback(path)


def test_corrupt_gzip_rejected(tmp_path):
    data = bytearray(gzip.compress(b'{"replay_version": 1}', mtime=0))
    data[-5] ^= 255
    path = tmp_path / "bad.pvzdemo"
    path.write_bytes(data)
    with pytest.raises((ValueError, OSError)):
        Playback(path)


def test_session_matches_api_and_midgame_duration(tmp_path):
    game, reference = Game(), Game()
    for instance in (game, reference):
        instance.reset()
        instance.step(ticks=17)
    with DemoSession(game, output=tmp_path / "game.pvzdemo") as demo:
        for action, ticks in [
            (Place("sunflower", 2, 0), 200),
            (Place("sunflower", 2, 0), 19),
            (Dig(2, 0), 4),
        ]:
            assert demo.step(action, ticks=ticks) == reference.step(action, ticks=ticks)
        result = demo.finish(outcome="truncated", termination_reason="sample_end")
        assert demo.finish() is result
        with pytest.raises(RuntimeError):
            demo.step()
    assert result.ticks_recorded == 223
    assert result.duration_seconds == 223 / 20
    assert result.final_hash == reference.state_hash()
    playback = Playback(result.path)
    assert playback.start_tick == 17 and playback.end_tick == 240
    assert playback.verify().observe() == result.observation
    assert playback.display_outcome == "truncated"
    assert len(playback.data["entries"]) == 3


def test_exception_preserves_completed_operations_and_original_exception(tmp_path):
    game = Game()
    game.reset()
    path = tmp_path / "partial.pvzdemo"
    with pytest.raises(LookupError, match="caller failed"):
        with DemoSession(game, output=path) as demo:
            demo.step(Place("sunflower", 2, 0), ticks=4)
            raise LookupError("caller failed")
    playback = Playback(path)
    assert playback.verify().state_hash() == game.state_hash()
    assert playback.end_tick == 4
    assert playback.display_outcome == "interrupted"
    assert playback.metadata["termination_reason"] == "caller_error"


def test_default_finish_empty_record_and_malformed_step(tmp_path):
    game = Game()
    game.reset()
    with DemoSession(game, output=tmp_path / "empty.pvzdemo") as demo:
        for action, ticks in [(Wait(), 0), (Place("sunflower", True, 0), 1)]:
            with pytest.raises((TypeError, ValueError)):
                demo.step(action, ticks=ticks)
        assert game.observe().tick == 0
        assert demo.recorder.entries == []
    playback = Playback(demo.result.path)
    assert playback.done and playback.end_tick == 0
    assert playback.display_outcome == "interrupted"
    assert playback.metadata["termination_reason"] == "recording_stopped"


def test_exclusive_publish_and_explicit_overwrite(tmp_path):
    path = tmp_path / "demo.pvzdemo"
    path.write_bytes(b"previous demo")
    with pytest.raises(FileExistsError):
        generate_demo(output=path, max_ticks=0)
    assert path.read_bytes() == b"previous demo"
    result = generate_demo(output=path, max_ticks=0, overwrite=True)
    assert Playback(result.path).display_outcome == "truncated"
    game = Game()
    game.reset()
    racing = tmp_path / "racing.pvzdemo"
    session = DemoSession(game, output=racing)
    racing.write_bytes(b"another writer")
    with pytest.raises(FileExistsError):
        session.finish()
    assert racing.read_bytes() == b"another writer"
    assert not list(tmp_path.glob(".pvz-*"))


def test_unrecorded_steps_are_not_silently_published(tmp_path):
    game = Game()
    game.reset()
    path = tmp_path / "bad.pvzdemo"
    session = DemoSession(game, output=path)
    game.step()
    with pytest.raises(ValueError, match="mismatch"):
        session.finish()
    assert not path.exists()


@pytest.mark.parametrize("max_ticks", [0, 1, 199, 200, 201, 437])
def test_generator_boundaries_gaps_rejections_and_same_tick_actions(tmp_path, max_ticks):
    scheduled = [
        ScheduledAction(0, Place("sunflower", 2, 0)),
        ScheduledAction(200, Place("sunflower", 2, 0)),
        ScheduledAction(201, Dig(2, 0)),
        ScheduledAction(300, Place("sunflower", -1000, 0)),
    ]
    result = generate_demo(actions=scheduled, output=tmp_path / "demo.pvzdemo", max_ticks=max_ticks)
    reference = Game()
    reference.reset()
    actions = {a.tick: a.action for a in scheduled}
    for tick in range(max_ticks):
        reference.step(actions.get(tick, Wait()))
    assert result.final_hash == reference.state_hash()
    assert result.observation.tick == max_ticks
    assert result.outcome == "truncated"
    playback = Playback(result.path)
    assert playback.verify().state_hash() == result.final_hash


@pytest.mark.parametrize("limit", [None, 1, 200])
def test_natural_outcome_precedes_limit_and_future_operations(tmp_path, limit):
    result = generate_demo(
        output=tmp_path / "won.pvzdemo",
        level=LevelSpec("empty"),
        max_ticks=limit,
        actions=[ScheduledAction(200, Place("sunflower", 0, 0))],
    )
    assert result.outcome == "won" and result.observation.tick == 1
    result = generate_demo(
        output=tmp_path / "lost.pvzdemo",
        level=LevelSpec("breach", (Spawn(1, "basic", 0, x=0),), mowers=False),
    )
    assert result.outcome == "lost"


@pytest.mark.parametrize(
    "actions",
    [
        [ScheduledAction(1, Wait()), ScheduledAction(1, Wait())],
        [ScheduledAction(1, Wait()), ScheduledAction(0, Wait())],
        [ScheduledAction(-1, Wait())],
        [ScheduledAction(True, Wait())],
        [ScheduledAction(1.5, Wait())],
        [ScheduledAction(1, "invalid")],
        [ScheduledAction(1, Place("sunflower", "0", 0))],
        [Wait()],
    ],
)
def test_invalid_schedule_rejected_before_output(tmp_path, actions):
    path = tmp_path / "uncreated" / "bad.pvzdemo"
    with pytest.raises((ValueError, TypeError)):
        generate_demo(output=path, actions=actions)
    assert not path.parent.exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_ticks": -1},
        {"max_ticks": True},
        {"speed": 3},
        {"speed": True},
        {"speed": float("nan")},
        {"live": 1},
    ],
)
def test_invalid_options_rejected_before_output(tmp_path, kwargs):
    path = tmp_path / "bad.pvzdemo"
    with pytest.raises((TypeError, ValueError)):
        generate_demo(output=path, **kwargs)
    assert not path.exists()


def test_cli_generate_verify_and_relative_scenario(tmp_path, capsys):
    (tmp_path / "scenario.toml").write_text('name = "empty"\nspawns = []\n')
    script = tmp_path / "script.toml"
    script.write_text('[demo]\nscenario = "scenario.toml"\n[metadata]\ntitle = "CLI demo"\n')
    options = load_demo_script(script)
    assert options["level"].name == "empty"
    path = tmp_path / "cli.pvzdemo"
    assert main(["demo", "--script", str(script), "--output", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "won"
    assert main(["replay", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["verified"]
    assert read_recording(path)["metadata"]["title"] == "CLI demo"


def test_headless_demo_does_not_import_pygame(tmp_path):
    code = """
import sys
from pvz_game.demo import generate_demo
generate_demo(output=sys.argv[1], max_ticks=4)
assert 'pygame' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "core.pvzdemo")], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "text",
    [
        "unexpected = 1",
        "[demo]\nunknown = true",
        '[demo]\nlevel = "easy"\nscenario = "absent.toml"',
        '[[actions]]\nkind = "wait"',
    ],
)
def test_malformed_scripts_are_rejected(tmp_path, text):
    script = tmp_path / "bad.toml"
    script.write_text(text)
    with pytest.raises(ValueError):
        load_demo_script(script)
