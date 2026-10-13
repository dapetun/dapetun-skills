"""Filesystem cache for unchanged skill analysis."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AnalysisCache:
    def __init__(self, directory: Path, enabled: bool = True) -> None:
        self.directory = directory
        self.enabled = enabled
        if enabled:
            self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, content_sha256: str) -> Path:
        return self.directory / f"{content_sha256}.json"

    def get(self, content_sha256: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        path = self._path(content_sha256)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Cache read failed for %s: %s", path, exc)
            return None

    def set(self, content_sha256: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        path = self._path(content_sha256)
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Cache write failed for %s: %s", path, exc)
