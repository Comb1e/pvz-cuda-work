"""Measure compact demo generation, file sizes, and exact-tick seeking on winning traces."""

import json
from pathlib import Path
from time import perf_counter

from pvz_game.demo import ScheduledAction, generate_demo
from pvz_game.replay import Playback, decode_action, read_recording


def main():
    output = Path("artifacts/demo-benchmarks")
    output.mkdir(parents=True, exist_ok=True)
    report = {}
    for level in ("easy", "standard", "hard"):
        fixture = read_recording(Path("tests/fixtures") / f"{level}-seed42.json")
        actions = tuple(
            ScheduledAction(e["tick"], decode_action(e["action"])) for e in fixture["entries"]
        )
        started = perf_counter()
        result = generate_demo(
            level=level,
            seed=42,
            actions=actions,
            output=output / f"{level}-seed42.pvzdemo",
            overwrite=True,
            metadata={"title": f"{level.title()} winning demonstration"},
        )
        generation = perf_counter() - started
        assert result.final_hash == fixture["final_hash"]
        playback = Playback(result.path)
        started = perf_counter()
        playback.seek(playback.end_tick)
        cold_seek = perf_counter() - started
        seek_times = []
        for i in range(100):
            target = (i * 7919) % (playback.end_tick + 1)
            started = perf_counter()
            playback.seek(target)
            seek_times.append(perf_counter() - started)
        playback.seek(playback.end_tick)
        assert playback.game.state_hash() == result.final_hash
        plain = (json.dumps(read_recording(result.path), separators=(",", ":")) + "\n").encode()
        report[level] = {
            "final_tick": result.observation.tick,
            "final_hash": result.final_hash,
            "compressed_bytes": result.path.stat().st_size,
            "json_bytes": len(plain),
            "generation_and_verification_seconds": round(generation, 4),
            "cold_seek_to_end_seconds": round(cold_seek, 4),
            "cached_seek_mean_ms": round(sum(seek_times) / len(seek_times) * 1000, 3),
            "cached_seek_max_ms": round(max(seek_times) * 1000, 3),
        }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
