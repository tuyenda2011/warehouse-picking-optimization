"""Canonical recursive Python-source inventory with portable relative keys."""
import hashlib
from pathlib import Path


def python_source_hashes(directory):
    root = Path(directory)
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*.py"))}
