"""SKILL.md parser aligned with agentskills.io specification."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from skill_optimizer.models import Frontmatter, SkillRecord, SkillResource
from skill_optimizer.security import (
    compile_injection_patterns,
    detect_injection,
    resolve_under_root,
    safe_read_text,
)
from skill_optimizer.textutil import (
    estimate_tokens,
    extract_capabilities,
    extract_exclusions,
    extract_markdown_links,
    extract_triggers,
    sha256_bytes,
    sha256_text,
)

logger = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def split_frontmatter(text: str) -> tuple[dict[str, Any] | None, str, str | None]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, text, "Missing YAML frontmatter delimited by ---"
    raw_yaml = match.group(1)
    body = match.group(2) or ""
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        return None, body, f"Invalid YAML frontmatter: {exc}"
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, body, "Frontmatter must be a YAML mapping"
    return data, body, None


def validate_name(name: str | None, directory_name: str) -> list[str]:
    issues: list[str] = []
    if not name:
        issues.append("Missing required frontmatter field: name")
        return issues
    if len(name) > 64:
        issues.append("name exceeds 64 characters")
    if not NAME_RE.fullmatch(name):
        issues.append(
            "name must be lowercase alphanumeric with single hyphens "
            "(no leading/trailing/consecutive hyphens)"
        )
    if name != directory_name:
        issues.append(f"name {name!r} does not match parent directory {directory_name!r}")
    return issues


def validate_description(description: str | None) -> list[str]:
    issues: list[str] = []
    if description is None or not str(description).strip():
        issues.append("Missing required frontmatter field: description")
        return issues
    if len(description) > 1024:
        issues.append("description exceeds 1024 characters")
    return issues


def parse_frontmatter(data: dict[str, Any] | None, parse_error: str | None) -> Frontmatter:
    if data is None:
        return Frontmatter(parse_error=parse_error)
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
        parse_error = (parse_error or "") + "; metadata must be a mapping"
    str_meta = {str(k): str(v) for k, v in metadata.items()}
    allowed = data.get("allowed-tools")
    if allowed is not None and not isinstance(allowed, str):
        allowed = str(allowed)
    return Frontmatter(
        name=str(data["name"]) if data.get("name") is not None else None,
        description=str(data["description"]) if data.get("description") is not None else None,
        license=str(data["license"]) if data.get("license") is not None else None,
        compatibility=str(data["compatibility"]) if data.get("compatibility") is not None else None,
        metadata=str_meta,
        allowed_tools=allowed,
        raw={str(k): v for k, v in data.items()},
        parse_error=parse_error,
    )


def collect_resources(skill_dir: Path) -> list[SkillResource]:
    resources: list[SkillResource] = []
    for kind in ("scripts", "references", "assets"):
        folder = skill_dir / kind
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(skill_dir).as_posix()
                data = path.read_bytes()
                resources.append(
                    SkillResource(
                        relative_path=rel,
                        kind=kind,
                        exists=True,
                        size_bytes=len(data),
                        sha256=sha256_bytes(data),
                    )
                )
            except OSError as exc:
                logger.warning("Unable to read resource %s: %s", path, exc)
    return resources


def check_links(skill_dir: Path, referenced: list[str]) -> list[str]:
    broken: list[str] = []
    for ref in referenced:
        try:
            target = resolve_under_root(skill_dir, ref)
        except Exception:
            broken.append(ref)
            continue
        if not target.exists():
            broken.append(ref)
    return broken


def build_skill_record(
    discovery: dict,
    *,
    injection_patterns: list[str],
    related_context_files: list[str],
) -> SkillRecord:
    skill_dir: Path = discovery["path"]
    skill_md: Path = discovery["skill_md_path"]
    text = safe_read_text(skill_md)
    content_hash = sha256_text(text)
    data, body, parse_error = split_frontmatter(text)
    fm = parse_frontmatter(data, parse_error)

    structural: list[str] = []
    if parse_error:
        structural.append(parse_error)
    structural.extend(validate_name(fm.name, skill_dir.name))
    structural.extend(validate_description(fm.description))
    if fm.compatibility is not None and len(fm.compatibility) > 500:
        structural.append("compatibility exceeds 500 characters")

    name = fm.name or skill_dir.name
    description = fm.description or ""
    patterns = compile_injection_patterns(injection_patterns)
    injection_flags = detect_injection(text, patterns)
    if injection_flags:
        structural.append("Potential prompt-injection markers detected in SKILL.md")

    referenced = extract_markdown_links(body)
    broken = check_links(skill_dir, referenced)
    if broken:
        structural.append(f"Broken relative references: {', '.join(broken)}")

    resources = collect_resources(skill_dir)
    skill_id = f"{discovery['platform'].value}:{discovery['scope'].value}:{name}:{content_hash[:12]}"

    return SkillRecord(
        skill_id=skill_id,
        path=skill_dir,
        skill_md_path=skill_md,
        name=name,
        platform=discovery["platform"],
        scope=discovery["scope"],
        origin=discovery["origin"],
        editable=discovery["editable"],
        frontmatter=fm,
        body=body,
        description=description,
        content_sha256=content_hash,
        body_sha256=sha256_text(body),
        resources=resources,
        referenced_paths=referenced,
        broken_links=broken,
        capabilities=extract_capabilities(description, body),
        triggers=extract_triggers(description, body),
        exclusions=extract_exclusions(description, body),
        injection_flags=injection_flags,
        structural_issues=structural,
        related_context_files=related_context_files,
        token_estimate=estimate_tokens(text),
    )
