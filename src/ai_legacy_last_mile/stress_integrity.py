"""Cross-platform integrity helpers for the frozen stress benchmark."""

import hashlib
import json
from pathlib import Path


def canonical_file_sha256(path: Path) -> str:
    """Hash a text file after canonicalizing CRLF line endings to LF."""

    canonical_bytes = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(canonical_bytes).hexdigest()


def verify_frozen_stress_benchmark(data_dir: Path | None = None) -> None:
    """Raise if any file protected by the freeze manifest has changed."""

    directory = data_dir or Path(__file__).resolve().parents[2] / "data" / "stress_benchmark"
    manifest = json.loads((directory / "freeze_manifest.json").read_text(encoding="utf-8"))
    mismatches = [
        name
        for name, expected in manifest["sha256"].items()
        if canonical_file_sha256(directory / name) != expected
    ]
    if mismatches:
        raise ValueError(f"frozen stress benchmark integrity failure: {', '.join(mismatches)}")
