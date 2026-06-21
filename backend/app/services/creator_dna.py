from __future__ import annotations

from pathlib import Path

from app.core.config import ROOT_DIR

_DEFAULT_PATH: Path = ROOT_DIR / "data" / "creator_dna.md"


def load_creator_dna(path: Path | None = None) -> str | None:
    """Load Creator DNA content from file.

    Returns stripped content if file exists and is non-empty,
    None if file is missing or empty.
    Never raises — caller is responsible for graceful degradation.
    """
    target = path or _DEFAULT_PATH
    try:
        if not target.is_file():
            return None
        content = target.read_text(encoding="utf-8").strip()
        return content if content else None
    except (OSError, UnicodeDecodeError):
        return None
