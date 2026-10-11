"""Configuration loading and platform path adapters."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skill_optimizer.simple_yaml import SimpleYAMLError, loads as yaml_loads

logger = logging.getLogger(__name__)

# skill-optimizer/skill_optimizer/config.py -> skill-optimizer/
SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = SKILL_ROOT / "config" / "default.yaml"


@dataclass
class OptimizerConfig:
    raw: dict[str, Any]
    project_root: Path
    home: Path
    platforms: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    extra_skill_roots: list[Path] = field(default_factory=list)
    min_severity: str = "medium"

    @property
    def thresholds(self) -> dict[str, Any]:
        return self.raw.get("thresholds", {})

    @property
    def weights(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.raw.get("weights", {}).items()}

    @property
    def security(self) -> dict[str, Any]:
        return self.raw.get("security", {})

    @property
    def discovery(self) -> dict[str, Any]:
        return self.raw.get("discovery", {})

    @property
    def apply(self) -> dict[str, Any]:
        return self.raw.get("apply", {})

    @property
    def cache(self) -> dict[str, Any]:
        return self.raw.get("cache", {})

    @property
    def validation(self) -> dict[str, Any]:
        return self.raw.get("validation", {})


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    try:
        data = yaml_loads(path.read_text(encoding="utf-8")) or {}
    except SimpleYAMLError as exc:
        raise ValueError(f"Invalid YAML config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return data


def load_config(
    config_path: Path | None = None,
    *,
    project_root: Path | None = None,
    home: Path | None = None,
    platforms: list[str] | None = None,
    scopes: list[str] | None = None,
    extra_skill_roots: list[Path] | None = None,
    min_severity: str | None = None,
) -> OptimizerConfig:
    base = load_yaml(DEFAULT_CONFIG_PATH) if DEFAULT_CONFIG_PATH.exists() else {}
    if config_path is not None:
        user_cfg = load_yaml(config_path)
        base = _deep_merge(base, user_cfg)
    cfg = OptimizerConfig(
        raw=base,
        project_root=(project_root or Path.cwd()).resolve(),
        home=(home or Path.home()).resolve(),
        platforms=platforms or list(base.get("platforms", [])),
        scopes=scopes or list(base.get("scopes", [])),
        extra_skill_roots=list(extra_skill_roots or []),
        min_severity=min_severity or str(base.get("reporting", {}).get("min_severity", "medium")),
    )
    logger.debug(
        "Loaded config project_root=%s platforms=%s scopes=%s",
        cfg.project_root,
        cfg.platforms,
        cfg.scopes,
    )
    return cfg


@dataclass(frozen=True)
class SkillRoot:
    path: Path
    platform: str
    scope: str
    origin: str
    editable: bool


def default_skill_roots(cfg: OptimizerConfig) -> list[SkillRoot]:
    """Return platform skill roots for Cursor, Claude Code, Codex, and Agents."""
    home = cfg.home
    project = cfg.project_root
    roots: list[SkillRoot] = []

    mapping: list[tuple[str, str, str, bool, Path]] = [
        ("cursor", "project", "local", True, project / ".cursor" / "skills"),
        ("cursor", "user", "local", True, home / ".cursor" / "skills"),
        (
            "cursor",
            "builtin",
            "plugin_cache",
            False,
            home / ".cursor" / "skills-cursor",
        ),
        ("agents", "project", "local", True, project / ".agents" / "skills"),
        ("agents", "user", "local", True, home / ".agents" / "skills"),
        ("claude", "project", "local", True, project / ".claude" / "skills"),
        ("claude", "user", "local", True, home / ".claude" / "skills"),
        ("codex", "project", "local", True, project / ".codex" / "skills"),
        ("codex", "user", "local", True, home / ".codex" / "skills"),
        ("codex", "project", "local", True, project / ".agents" / "skills"),
    ]

    seen: set[Path] = set()
    for platform, scope, origin, editable, path in mapping:
        if platform not in cfg.platforms and "all" not in cfg.platforms:
            continue
        if scope not in cfg.scopes and "all" not in cfg.scopes:
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(
            SkillRoot(
                path=resolved,
                platform=platform,
                scope=scope,
                origin=origin,
                editable=editable and scope in {"user", "project"},
            )
        )

    for extra in cfg.extra_skill_roots:
        resolved = extra.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(
            SkillRoot(
                path=resolved,
                platform="agents",
                scope="project",
                origin="synthetic",
                editable=True,
            )
        )
    return roots
