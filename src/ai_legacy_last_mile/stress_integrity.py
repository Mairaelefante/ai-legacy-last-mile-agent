"""Cross-platform integrity helpers for the frozen stress benchmark."""

import hashlib
from pathlib import Path


def canonical_file_sha256(path: Path) -> str:
    """Hash a text file after canonicalizing CRLF line endings to LF."""

    canonical_bytes = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(canonical_bytes).hexdigest()
