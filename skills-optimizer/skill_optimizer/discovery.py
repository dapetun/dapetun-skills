"""Discovery engine for Agent Skills across platforms and scopes."""

from __future__ import annotations

import logging
from pathlib import Path

from skill_optimizer.config import OptimizerConfig, SkillRoot, default_skill_roots
from skill_optimizer.models import Origin, Platform, Scope

logger = logging.getLogger(__name__)


def _to_platform(value: str) -> Platform:
    try:
        return Platform(value)
    except ValueError:
        return Platform.UNKNOWN


def _to_scope(value: str) -> Scope:
    try:
        return Scope(value)
    except ValueError:
        return Scope.UNKNOWN


def _to_origin(value: str) -> Origin:
    try:
        return Origin(value)
    except ValueError:
        return Origin.LOCAL


def find_related_context_files(project_root: Path, names: list[str]) -> list[str]:
    found: list[str] = []
    for name in names:
        path = project_root / name
        if path.is_file():
            found.append(str(path.resolve()))
    # Cursor rules directory is related context, not a skill source
    rules_dir = project_root / ".cursor" / "rules"
    if rules_dir.is_dir():
        found.append(str(rules_dir.resolve()))
    return found


def discover_skill_md_files(
    root: SkillRoot,
    *,
    max_depth: int,
    skip_dir_names: set[str],
    follow_symlinks: bool,
) -> list[Path]:
    if not root.path.exists() or not root.path.is_dir():
        logger.debug("Skill root missing or not a directory: %s", root.path)
        return []

    results: list[Path] = []
    root_depth = len(root.path.resolve().parts)

    for dirpath, dirnames, filenames in _walk(root.path, follow_symlinks):
        current = Path(dirpath)
        depth = len(current.resolve().parts) - root_depth
        if depth > max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in skip_dir_names and not d.startswith(".")]
        if "SKILL.md" in filenames:
            skill_md = current / "SKILL.md"
            try:
                if skill_md.is_file():
                    results.append(skill_md.resolve())
            except OSError as exc:
                logger.warning("Skipping inaccessible skill file under %s: %s", current, exc)
    return sorted(set(results))


def _walk(path: Path, follow_symlinks: bool):
    """os.walk-like generator with symlink control."""
    import os

    for dirpath, dirnames, filenames in os.walk(path, followlinks=follow_symlinks):
        yield dirpath, dirnames, filenames


def discover_skills(cfg: OptimizerConfig) -> tuple[list[dict], list[str]]:
    """
    Discover skill directories.

    Returns a list of discovery records (not yet fully parsed) and related context files.
    """
    roots = default_skill_roots(cfg)
    max_depth = int(cfg.discovery.get("max_depth", 8))
    skip = set(cfg.discovery.get("skip_dir_names", []))
    follow = bool(cfg.discovery.get("follow_symlinks", False))
    related = find_related_context_files(
        cfg.project_root, list(cfg.discovery.get("related_files", []))
    )

    records: list[dict] = []
    seen_paths: set[Path] = set()

    for root in roots:
        for skill_md in discover_skill_md_files(
            root, max_depth=max_depth, skip_dir_names=skip, follow_symlinks=follow
        ):
            skill_dir = skill_md.parent
            if skill_dir in seen_paths:
                continue
            seen_paths.add(skill_dir)
            records.append(
                {
                    "path": skill_dir,
                    "skill_md_path": skill_md,
                    "platform": _to_platform(root.platform),
                    "scope": _to_scope(root.scope),
                    "origin": _to_origin(root.origin),
                    "editable": bool(root.editable),
                }
            )
            logger.info(
                "Discovered skill candidate path=%s platform=%s scope=%s",
                skill_dir,
                root.platform,
                root.scope,
            )

    logger.info("Discovery complete: %d skills, %d related context files", len(records), len(related))
    return records, related
