"""Safe apply engine with snapshots, staging, and rollback."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skill_optimizer.config import OptimizerConfig
from skill_optimizer.models import OperationType, OptimizationPlan, Recommendation, SkillRecord
from skill_optimizer.security import SecurityError, assert_editable, safe_read_text
from skill_optimizer.textutil import sha256_text
from skill_optimizer.validation import validate_plan_hashes

logger = logging.getLogger(__name__)


@dataclass
class ApplyResult:
    ok: bool
    dry_run: bool
    snapshot_id: str | None
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    diffs: list[dict[str, Any]] = field(default_factory=list)
    rolled_back: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _snapshot_root(cfg: OptimizerConfig) -> Path:
    return (cfg.project_root / cfg.apply.get("snapshot_directory", ".skill-optimizer/snapshots")).resolve()


def _staging_root(cfg: OptimizerConfig) -> Path:
    return (cfg.project_root / cfg.apply.get("staging_directory", ".skill-optimizer/staging")).resolve()


def create_snapshot(skills: list[SkillRecord], cfg: OptimizerConfig) -> str:
    snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    root = _snapshot_root(cfg) / snapshot_id
    root.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "skills": [],
    }
    for skill in skills:
        if not skill.editable:
            continue
        dest = root / skill.skill_id.replace(":", "__")
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill.path, dest / "skill", dirs_exist_ok=True)
        manifest["skills"].append(
            {
                "skill_id": skill.skill_id,
                "path": str(skill.path),
                "content_sha256": skill.content_sha256,
                "snapshot_path": str(dest / "skill"),
            }
        )
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Created snapshot %s with %d editable skills", snapshot_id, len(manifest["skills"]))
    return snapshot_id


def rollback(snapshot_id: str, cfg: OptimizerConfig) -> ApplyResult:
    root = _snapshot_root(cfg) / snapshot_id
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return ApplyResult(
            ok=False,
            dry_run=False,
            snapshot_id=snapshot_id,
            errors=[f"Snapshot not found: {snapshot_id}"],
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    restored: list[str] = []
    for item in manifest.get("skills", []):
        src = Path(item["snapshot_path"])
        dest = Path(item["path"])
        try:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            restored.append(item["skill_id"])
        except OSError as exc:
            errors.append(f"{item['skill_id']}: {exc}")
    return ApplyResult(
        ok=not errors,
        dry_run=False,
        snapshot_id=snapshot_id,
        applied=restored,
        errors=errors,
        rolled_back=True,
    )


def _skill_by_id(skills: list[SkillRecord], skill_id: str) -> SkillRecord | None:
    for skill in skills:
        if skill.skill_id == skill_id:
            return skill
    return None


def preview_diff(skill: SkillRecord, new_text: str) -> dict[str, Any]:
    old = safe_read_text(skill.skill_md_path)
    return {
        "skill_id": skill.skill_id,
        "path": str(skill.skill_md_path),
        "old_sha256": sha256_text(old),
        "new_sha256": sha256_text(new_text),
        "old_preview": old[:500],
        "new_preview": new_text[:500],
        "changed": old != new_text,
    }


def _write_via_staging(target: Path, content: str, staging_dir: Path) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_file = staging_dir / f"{uuid.uuid4().hex}.tmp"
    staging_file.write_text(content, encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staging_file), str(target))


def _apply_fix_structure(skill: SkillRecord) -> str:
    text = safe_read_text(skill.skill_md_path)
    name = skill.path.name
    description = skill.description or f"{name} skill. Use when relevant to {name.replace('-', ' ')}."
    if len(description) > 1024:
        description = description[:1021] + "..."
    # Rebuild minimal valid frontmatter; preserve body.
    body = skill.body
    if skill.frontmatter.parse_error or not skill.frontmatter.name:
        body = body if body.strip() else "# Instructions\n\nTODO: restore instructions.\n"
    lines = [
        "---",
        f"name: {name}",
        f"description: {json.dumps(description, ensure_ascii=False)}",
    ]
    if skill.frontmatter.license:
        lines.append(f"license: {skill.frontmatter.license}")
    lines.append("---")
    lines.append("")
    # Strip injection-like lines from body for safety when rewriting structure/injection
    cleaned_lines = []
    for line in body.splitlines():
        low = line.lower()
        if "ignore previous instructions" in low or "disregard prior" in low:
            cleaned_lines.append("<!-- removed untrusted injection-like line -->")
            continue
        cleaned_lines.append(line)
    lines.append("\n".join(cleaned_lines).rstrip() + "\n")
    return "\n".join(lines)


def _apply_refine_description(skill: SkillRecord) -> str:
    text = safe_read_text(skill.skill_md_path)
    desc = skill.description
    # Narrow broad descriptions: keep first sentence + explicit use-when from name
    first = desc.split(".")[0].strip()
    refined = (
        f"{first}. Use when working specifically with {skill.name.replace('-', ' ')}. "
        f"Do not use for unrelated general tasks."
    )
    if len(refined) > 1024:
        refined = refined[:1021] + "..."
    # Replace description field in frontmatter
    import re

    new_text, n = re.subn(
        r"(?m)^description:\s*.*$",
        f"description: {json.dumps(refined, ensure_ascii=False)}",
        text,
        count=1,
    )
    if n == 0:
        return _apply_fix_structure(skill)
    return new_text


def _apply_deprecate(skill: SkillRecord) -> str:
    text = safe_read_text(skill.skill_md_path)
    notice = (
        "\n\n> **DEPRECATED**: Exact duplicate detected by skill-optimizer. "
        "Prefer the canonical skill with the same content hash. "
        "Kept for rollback safety; safe to remove after confirmation.\n"
    )
    if "DEPRECATED" in text:
        return text
    return text.rstrip() + notice


def _apply_merge(skills: list[SkillRecord], cfg: OptimizerConfig) -> tuple[SkillRecord, str, list[str]]:
    """Merge into the first editable skill; copy resources from others."""
    target = next((s for s in skills if s.editable), skills[0])
    caps = []
    bodies = []
    for s in skills:
        caps.extend(s.capabilities)
        bodies.append(f"## From `{s.name}`\n\n{s.body.strip()}\n")
    # Dedupe capabilities for description
    uniq_caps = []
    seen = set()
    for c in caps:
        if c not in seen:
            seen.add(c)
            uniq_caps.append(c)
    description = (
        f"Merged skill covering: {', '.join(s.name for s in skills)}. "
        f"Use when any of these apply: {'; '.join(uniq_caps[:5])}."
    )[:1024]
    content = (
        "---\n"
        f"name: {target.path.name}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        "# Merged instructions\n\n"
        + "\n".join(bodies)
    )
    copied_resources: list[str] = []
    for s in skills:
        if s.skill_id == target.skill_id:
            continue
        for resource in s.resources:
            src = s.path / resource.relative_path
            dest = target.path / resource.relative_path
            if not src.exists():
                continue
            # Avoid overwrite collisions by namespacing
            if dest.exists():
                dest = target.path / resource.kind / f"from_{s.name}_{Path(resource.relative_path).name}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied_resources.append(str(dest))
    return target, content, copied_resources


def apply_plan(
    plan: OptimizationPlan,
    skills: list[SkillRecord],
    cfg: OptimizerConfig,
    *,
    dry_run: bool = True,
    confirm: bool = False,
    recommendation_ids: list[str] | None = None,
) -> ApplyResult:
    hash_check = validate_plan_hashes(plan, skills)
    if not hash_check.passed:
        return ApplyResult(
            ok=False,
            dry_run=dry_run,
            snapshot_id=None,
            errors=[hash_check.detail],
        )

    if not dry_run and not confirm:
        return ApplyResult(
            ok=False,
            dry_run=False,
            snapshot_id=None,
            errors=["Refusing to apply without --confirm (read-only by default)."],
        )

    selected = plan.recommendations
    if recommendation_ids:
        selected = [r for r in plan.recommendations if r.recommendation_id in recommendation_ids]

    snapshot_id = None
    if not dry_run:
        snapshot_id = create_snapshot(skills, cfg)

    result = ApplyResult(ok=True, dry_run=dry_run, snapshot_id=snapshot_id)
    staging = _staging_root(cfg) / (snapshot_id or "dry-run")
    allow_scopes = list(cfg.apply.get("allow_edit_scopes", ["user", "project"]))
    forbid_origins = list(cfg.apply.get("forbid_edit_origins", []))

    try:
        for rec in selected:
            _apply_recommendation(
                rec,
                skills,
                cfg,
                result=result,
                dry_run=dry_run,
                staging=staging,
                allow_scopes=allow_scopes,
                forbid_origins=forbid_origins,
            )
    except Exception as exc:
        logger.exception("Apply failed: %s", exc)
        result.ok = False
        result.errors.append(str(exc))
        if snapshot_id and not dry_run:
            rb = rollback(snapshot_id, cfg)
            result.rolled_back = True
            if not rb.ok:
                result.errors.extend(rb.errors)

    # Persist execution manifest
    manifest_dir = cfg.project_root / ".skill-optimizer"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "execution-manifest.json"
    history: list[dict[str, Any]] = []
    if manifest_path.exists():
        try:
            history = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except json.JSONDecodeError:
            history = []
    history.append(
        {
            "plan_id": plan.plan_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result": result.to_dict(),
        }
    )
    manifest_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _apply_recommendation(
    rec: Recommendation,
    skills: list[SkillRecord],
    cfg: OptimizerConfig,
    *,
    result: ApplyResult,
    dry_run: bool,
    staging: Path,
    allow_scopes: list[str],
    forbid_origins: list[str],
) -> None:
    if rec.operation == OperationType.NO_CHANGE:
        result.skipped.append(rec.recommendation_id)
        return

    targets = [_skill_by_id(skills, sid) for sid in rec.skill_ids]
    targets = [t for t in targets if t is not None]
    if not targets:
        result.skipped.append(rec.recommendation_id)
        return

    try:
        if rec.operation == OperationType.MERGE_SKILLS:
            for t in targets:
                assert_editable(
                    editable=t.editable,
                    scope=t.scope.value,
                    origin=t.origin.value,
                    allow_edit_scopes=allow_scopes,
                    forbid_edit_origins=forbid_origins,
                )
            target, content, copied = _apply_merge(targets, cfg)
            diff = preview_diff(target, content)
            result.diffs.append({**diff, "copied_resources": copied, "operation": rec.operation.value})
            if not dry_run and diff["changed"]:
                _write_via_staging(target.skill_md_path, content, staging)
            # Soft-deprecate others
            for other in targets:
                if other.skill_id == target.skill_id:
                    continue
                dep = _apply_deprecate(other)
                d2 = preview_diff(other, dep)
                result.diffs.append(d2)
                if not dry_run and d2["changed"]:
                    _write_via_staging(other.skill_md_path, dep, staging)
            result.applied.append(rec.recommendation_id)
            return

        # Single-target ops (apply to editable skills only)
        for skill in targets:
            if not skill.editable:
                result.skipped.append(f"{rec.recommendation_id}:{skill.skill_id}:not-editable")
                continue
            assert_editable(
                editable=skill.editable,
                scope=skill.scope.value,
                origin=skill.origin.value,
                allow_edit_scopes=allow_scopes,
                forbid_edit_origins=forbid_origins,
            )
            if rec.operation in {
                OperationType.FIX_STRUCTURE,
                OperationType.REWRITE_INSTRUCTIONS,
            }:
                content = _apply_fix_structure(skill)
            elif rec.operation == OperationType.REFINE_DESCRIPTION:
                content = _apply_refine_description(skill)
            elif rec.operation == OperationType.DEPRECATE_SKILL:
                hints = rec.patch_hints or {}
                if skill.skill_id == hints.get("keep_skill_id"):
                    result.skipped.append(f"{rec.recommendation_id}:{skill.skill_id}:keep")
                    continue
                content = _apply_deprecate(skill)
            elif rec.operation == OperationType.CHANGE_SCOPE:
                # Non-destructive: add notice rather than moving directories automatically
                content = safe_read_text(skill.skill_md_path)
                if "SCOPE NOTE" not in content:
                    prefer = (rec.patch_hints or {}).get("prefer_scope", "project")
                    content = (
                        content.rstrip()
                        + f"\n\n> **SCOPE NOTE**: Canonical scope preferred by optimizer: `{prefer}`.\n"
                    )
            elif rec.operation == OperationType.EXTRACT_SHARED_RESOURCE:
                content = safe_read_text(skill.skill_md_path)
                ref = "references/shared-overlap.md"
                ref_path = skill.path / ref
                if not dry_run:
                    ref_path.parent.mkdir(parents=True, exist_ok=True)
                    if not ref_path.exists():
                        ref_path.write_text(
                            "# Shared guidance\n\nExtracted overlap notes. Review and trim.\n",
                            encoding="utf-8",
                        )
                if ref not in content:
                    content = content.rstrip() + f"\n\nSee [{ref}]({ref}) for shared guidance.\n"
            elif rec.operation == OperationType.SPLIT_SKILL:
                content = safe_read_text(skill.skill_md_path)
                if "SPLIT CANDIDATE" not in content:
                    content = (
                        content.rstrip()
                        + "\n\n> **SPLIT CANDIDATE**: Consider splitting this skill into narrower specialties.\n"
                    )
            else:
                result.skipped.append(f"{rec.recommendation_id}:{rec.operation.value}")
                continue

            diff = preview_diff(skill, content)
            result.diffs.append({**diff, "operation": rec.operation.value})
            if not dry_run and diff["changed"]:
                _write_via_staging(skill.skill_md_path, content, staging)
            result.applied.append(f"{rec.recommendation_id}:{skill.skill_id}")
    except SecurityError as exc:
        result.ok = False
        result.errors.append(f"{rec.recommendation_id}: {exc}")
        raise
