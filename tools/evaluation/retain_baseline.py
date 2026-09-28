"""Retain source and historical manifests locally without changing their bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

BASELINE_COMMIT = "af7c5e4d0593a6354feebbd0bbbe0c8d687d01a3"


def retain(root: Path, output: Path, manifests: list[Path]) -> dict:
    # Refuse reuse of a snapshot directory; a missing receipt does not make an empty freeze.
    if not manifests or any(not path.is_file() for path in manifests):
        raise ValueError("existing historical manifests are required")
    subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", BASELINE_COMMIT + "^{commit}"],
        check=True,
        capture_output=True,
    )
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    archive = output / "baseline-source.tar"
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "archive",
            "--format=tar",
            "--output=" + str(archive.resolve()),
            BASELINE_COMMIT,
        ],
        check=True,
        capture_output=True,
    )
    records = []
    for index, source in enumerate(manifests):
        data = source.read_bytes()
        target = output / f"historical-{index + 1:02}.json"
        with target.open("xb") as handle:
            handle.write(data)
        records.append(
            {
                "snapshot": target.name,
                "source": str(source.resolve()),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    record = {
        "schema": "payable-ocr-retained-baseline/1",
        "commit": BASELINE_COMMIT,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "historical_manifests": records,
        "contains_private_metadata": True,
    }
    with (output / "retention.json").open("x") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path, action="append")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[2]
        retain(root, args.output, args.manifest)
    except (OSError, ValueError, subprocess.SubprocessError):
        parser.exit(2, "Baseline retention failed; no existing snapshot was overwritten.\n")
    print(
        "Retained source archive and byte-identical historical manifests. Keep the directory private."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
