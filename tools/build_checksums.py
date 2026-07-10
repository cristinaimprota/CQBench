from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "MANIFEST.sha256"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


# Directories that are not part of the published benchmark artifact:
# caches, git internals, editable-install metadata, and experiment output.
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".git", "runs"}


def _excluded(path: Path) -> bool:
    return any(
        part in EXCLUDED_PARTS or part.endswith(".egg-info")
        for part in path.relative_to(ROOT).parts
    )


paths = sorted(
    path
    for path in ROOT.rglob("*")
    if path.is_file() and path != OUTPUT and not _excluded(path)
)
lines = [
    f"{digest(path)}  {path.relative_to(ROOT).as_posix()}"
    for path in paths
]
OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Wrote {len(lines)} checksums to {OUTPUT}")
