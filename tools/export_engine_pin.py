"""Export a source pin after committing the engine revision; no consumer project is edited."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pvz_game
from pvz_game import ENGINE_VERSION, PACKAGE_VERSION, Rules


def source_manifest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.suffix in (".py", ".toml")
    }


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=root / "dist" / f"engine-lock-{PACKAGE_VERSION}.json"
    )
    args = parser.parse_args()

    if Path(pvz_game.__file__).resolve().parent != root / "src" / "pvz_game":
        raise SystemExit("Use this checkout's editable installation to export its source pin.")

    def git(*options):
        return subprocess.run(
            ["git", "-C", str(root), *options], capture_output=True, text=True, check=True
        ).stdout.strip()

    if git("status", "--porcelain", "--", "src/pvz_game", "pyproject.toml"):
        raise SystemExit("Commit package source before exporting its pin.")
    data = {
        "commit": git("rev-parse", "HEAD"),
        "version": ENGINE_VERSION,
        "package_version": PACKAGE_VERSION,
        "rules_hash": Rules().digest,
        "files": source_manifest(root / "src" / "pvz_game"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
