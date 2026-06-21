from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings


def _build_file_handler(path: Path) -> logging.Handler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    return handler


def setup_logging() -> None:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    for name in ["download", "render", "validation", "error"]:
        root.addHandler(_build_file_handler(settings.logs_dir / f"{name}.log"))
