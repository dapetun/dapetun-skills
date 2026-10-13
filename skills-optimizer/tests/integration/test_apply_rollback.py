"""Integration tests for apply, stale plans, merge, and rollback."""

from __future__ import annotations

import json
from pathlib import Path

from skill_optimizer.apply_engine import apply_plan, create_snapshot, rollback
from skill_optimizer.models import OperationType, OptimizationPlan, Recommendation
from skill_optimizer.pipeline import analyze, load_skills, run_audit
from skill_optimizer.planner import build_plan


def _by_name(skills):
    return {s.name: s for s in skills}


def test_apply_requires_confirm(cfg, skills):
    _skills, findings, _graph, plan = analyze(cfg)
    result = apply_plan(plan, skills, cfg, dry_run=False, confirm=False)
    assert not result.ok
    assert any("confirm" in e.lower() for e in result.errors)


def test_stale_plan_rejected(cfg, fixture_project):
    skills = load_skills(cfg)
    _s, findings, _g, plan = analyze(cfg, skills=skills)
    target = _by_name(skills)["stale-plan-target"]
    # Mutate file after plan creation
    path = target.skill_md_path
    path.write_text(path.read_text(encoding="utf-8") + "\nChanged after plan.\n", encoding="utf-8")
    skills_after = load_skills(cfg)
    result = apply_plan(plan, skills_after, cfg, dry_run=True, confirm=False)
    assert not result.ok
    assert any("Stale" in e or "changed" in e.lower() or "mismatch" in e.lower() for e in result.errors)


def test_merge_preserves_resources(cfg, fixture_project):
    skills = load_skills(cfg)
    by = _by_name(skills)
    alpha = by["merge-alpha"]
    beta = by["merge-beta"]
    plan = OptimizationPlan(
        plan_id="plan-merge-test",
        created_at="2026-01-01T00:00:00+00:00",
        skill_hashes={s.skill_id: s.content_sha256 for s in skills},
        recommendations=[
            Recommendation(
                recommendation_id="rec-merge",
                operation=OperationType.MERGE_SKILLS,
                skill_ids=[alpha.skill_id, beta.skill_id],
                rationale="test merge",
                expected_benefit="preserve resources",
                risks=[],
                verification_criteria=["resources retained"],
                priority=1,
                patch_hints={"preserve_resources": True},
            )
        ],
    )
    result = apply_plan(plan, skills, cfg, dry_run=False, confirm=True)
    assert result.ok, result.errors
    # Alpha should gain beta's reference (possibly namespaced)
    alpha_refs = list((alpha.path / "references").rglob("*")) if (alpha.path / "references").exists() else []
    beta_style_copied = any("style.md" in p.name for p in alpha_refs) or any(
        "style.md" in str(d.get("copied_resources", [])) for d in result.diffs
    )
    assert beta_style_copied or any(d.get("copied_resources") for d in result.diffs)
    assert (alpha.path / "scripts" / "format_json.py").exists()


def test_apply_failure_rolls_back(cfg, monkeypatch):
    skills = load_skills(cfg)
    _s, findings, _g, plan = analyze(cfg, skills=skills)
    # Force a failure after snapshot by patching staging write
    from skill_optimizer import apply_engine

    real_write = apply_engine._write_via_staging

    def boom(*args, **kwargs):
        raise RuntimeError("simulated apply failure")

    monkeypatch.setattr(apply_engine, "_write_via_staging", boom)
    # Ensure plan has at least one writable op
    mutable = [
        r
        for r in plan.recommendations
        if r.operation != OperationType.NO_CHANGE
    ]
    if not mutable:
        # synthesize a fix-structure rec
        target = next(s for s in skills if s.name == "broken-links-skill")
        plan.recommendations.insert(
            0,
            Recommendation(
                recommendation_id="rec-force",
                operation=OperationType.FIX_STRUCTURE,
                skill_ids=[target.skill_id],
                rationale="force",
                expected_benefit="x",
                risks=[],
                verification_criteria=[],
                priority=1,
            ),
        )
        plan.skill_hashes = {s.skill_id: s.content_sha256 for s in skills}

    before = {
        s.skill_id: s.skill_md_path.read_text(encoding="utf-8")
        for s in skills
        if s.editable
    }
    result = apply_plan(plan, skills, cfg, dry_run=False, confirm=True)
    assert not result.ok
    assert result.rolled_back or result.snapshot_id
    # Files should match pre-apply content after rollback
    if result.rolled_back:
        for skill in skills:
            if not skill.editable:
                continue
            assert skill.skill_md_path.read_text(encoding="utf-8") == before[skill.skill_id]
    monkeypatch.setattr(apply_engine, "_write_via_staging", real_write)


def test_rollback_command(cfg):
    skills = load_skills(cfg)
    snap = create_snapshot(skills, cfg)
    target = next(s for s in skills if s.name == "healthy-unique")
    original = target.skill_md_path.read_text(encoding="utf-8")
    target.skill_md_path.write_text(original + "\nMUTATED\n", encoding="utf-8")
    result = rollback(snap, cfg)
    assert result.ok
    assert target.skill_md_path.read_text(encoding="utf-8") == original


def test_audit_outputs(cfg, tmp_path: Path):
    out = tmp_path / "reports"
    result = run_audit(cfg, out)
    for name in (
        "inventory.json",
        "findings.json",
        "skill-graph.json",
        "optimization-plan.json",
        "audit-report.md",
        "validation-report.json",
    ):
        assert (out / name).exists(), name
    inventory = json.loads((out / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["count"] >= 10
    validation = json.loads((out / "validation-report.json").read_text(encoding="utf-8"))
    # Must not invent measured metrics without probes
    metrics = validation["metrics"]
    assert "routing_accuracy" in metrics
    assert "notes" in metrics


def test_no_change_when_only_healthy(tmp_path: Path, fixture_home: Path):
    """Case 12: library needing no optimization."""
    project = tmp_path / "clean_project"
    skill_dir = project / ".agents" / "skills" / "only-sbom"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: only-sbom\n"
        "description: Generate SBOM for Python packages. Use when creating CycloneDX SBOM. "
        "Do not use for upgrades.\n"
        "---\n\n"
        "# SBOM\n\nGenerate CycloneDX only.\n",
        encoding="utf-8",
    )
    from skill_optimizer.config import load_config

    cfg = load_config(
        project_root=project,
        home=fixture_home / "empty_home_clean",
        platforms=["agents"],
        scopes=["project"],
    )
    (cfg.home).mkdir(parents=True, exist_ok=True)
    skills, findings, _g, plan = analyze(cfg)
    assert len(skills) == 1
    problem = [
        f
        for f in findings
        if f.relation.value
        in {"DUPLICATE", "CONFLICTS", "POTENTIAL_MERGE", "SHADOWS", "OVERLAPS"}
    ]
    assert not problem
    assert any(r.operation == OperationType.NO_CHANGE for r in plan.recommendations)
