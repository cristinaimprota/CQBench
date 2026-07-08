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


paths = sorted(
    path
    for path in ROOT.rglob("*")
    if path.is_file()
    and path != OUTPUT
    and "__pycache__" not in path.parts
    and ".pytest_cache" not in path.parts
)
lines = [
    f"{digest(path)}  {path.relative_to(ROOT).as_posix()}"
    for path in paths
]
OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Wrote {len(lines)} checksums to {OUTPUT}")
