"""End-to-end orchestration for audit / plan / check flows."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from skill_optimizer.cache import AnalysisCache
from skill_optimizer.config import OptimizerConfig
from skill_optimizer.conflict_graph import build_conflict_graph
from skill_optimizer.discovery import discover_skills
from skill_optimizer.models import Finding, OptimizationPlan, SkillRecord
from skill_optimizer.parser import build_skill_record
from skill_optimizer.planner import build_plan
from skill_optimizer.reporting import write_all_reports
from skill_optimizer.semantic_analyzer import analyze_semantic
from skill_optimizer.static_analyzer import analyze_static
from skill_optimizer.validation import run_validation

logger = logging.getLogger(__name__)


def load_skills(cfg: OptimizerConfig) -> list[SkillRecord]:
    discoveries, related = discover_skills(cfg)
    cache_dir = cfg.project_root / cfg.cache.get("directory", ".skill-optimizer/cache")
    cache = AnalysisCache(cache_dir, enabled=bool(cfg.cache.get("enabled", True)))
    injection_patterns = list(cfg.security.get("injection_patterns", []))

    skills: list[SkillRecord] = []
    for item in discoveries:
        # Parse first to get hash; cache stores semantic extracts only as hint.
        record = build_skill_record(
            item,
            injection_patterns=injection_patterns,
            related_context_files=related,
        )
        cached = cache.get(record.content_sha256)
        if cached:
            record.capabilities = list(cached.get("capabilities", record.capabilities))
            record.triggers = list(cached.get("triggers", record.triggers))
            record.exclusions = list(cached.get("exclusions", record.exclusions))
            record.cached = True
        else:
            cache.set(
                record.content_sha256,
                {
                    "capabilities": record.capabilities,
                    "triggers": record.triggers,
                    "exclusions": record.exclusions,
                    "name": record.name,
                },
            )
        skills.append(record)
    return skills


def analyze(
    cfg: OptimizerConfig,
    *,
    skills: list[SkillRecord] | None = None,
) -> tuple[list[SkillRecord], list[Finding], dict[str, Any], OptimizationPlan]:
    skills = skills if skills is not None else load_skills(cfg)
    static_findings = analyze_static(skills, cfg)
    semantic_findings = analyze_semantic(skills, cfg)
    findings = _dedupe_findings(static_findings + semantic_findings)
    graph = build_conflict_graph(skills, findings, cfg)
    plan = build_plan(skills, findings, cfg)
    return skills, findings, graph, plan


def run_audit(cfg: OptimizerConfig, output_dir: Path) -> dict[str, Any]:
    skills, findings, graph, plan = analyze(cfg)
    validation_results, metrics = run_validation(skills, findings, cfg, plan=plan)
    paths = write_all_reports(
        output_dir,
        skills=skills,
        findings=findings,
        graph=graph,
        plan=plan,
        validation_results=validation_results,
        metrics=metrics,
    )
    return {
        "skills": skills,
        "findings": findings,
        "graph": graph,
        "plan": plan,
        "validation": validation_results,
        "metrics": metrics,
        "paths": {k: str(v) for k, v in paths.items()},
    }


def run_plan(cfg: OptimizerConfig, output_dir: Path) -> dict[str, Any]:
    # Plan mode is audit + explicit plan emphasis (same artifacts).
    return run_audit(cfg, output_dir)


def run_check(cfg: OptimizerConfig, skill_path: Path, output_dir: Path) -> dict[str, Any]:
    """Check a single skill path (new or changed)."""
    skill_path = skill_path.resolve()
    skill_md = skill_path / "SKILL.md" if skill_path.is_dir() else skill_path
    if skill_md.name != "SKILL.md":
        raise FileNotFoundError(f"Expected SKILL.md, got {skill_md}")
    skill_dir = skill_md.parent
    from skill_optimizer.models import Origin, Platform, Scope

    discovery = {
        "path": skill_dir,
        "skill_md_path": skill_md,
        "platform": Platform.AGENTS,
        "scope": Scope.PROJECT,
        "origin": Origin.LOCAL,
        "editable": True,
    }
    related = []
    record = build_skill_record(
        discovery,
        injection_patterns=list(cfg.security.get("injection_patterns", [])),
        related_context_files=related,
    )
    # Also load ecosystem for interaction checks
    others = [s for s in load_skills(cfg) if s.path != skill_dir]
    skills = others + [record]
    static_findings = analyze_static([record], cfg)
    # Semantic against full set but keep findings that involve the target
    semantic_findings = [
        f
        for f in analyze_semantic(skills, cfg)
        if record.skill_id in f.skill_ids or len(f.skill_ids) == 1
    ]
    findings = _dedupe_findings(static_findings + semantic_findings)
    graph = build_conflict_graph(skills, findings, cfg)
    plan = build_plan([record], findings, cfg)
    validation_results, metrics = run_validation([record], findings, cfg, plan=plan)
    paths = write_all_reports(
        output_dir,
        skills=[record],
        findings=findings,
        graph=graph,
        plan=plan,
        validation_results=validation_results,
        metrics=metrics,
    )
    return {
        "skill": record,
        "findings": findings,
        "plan": plan,
        "validation": validation_results,
        "metrics": metrics,
        "paths": {k: str(v) for k, v in paths.items()},
    }


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    seen: set[str] = set()
    out: list[Finding] = []
    for finding in findings:
        if finding.finding_id in seen:
            continue
        seen.add(finding.finding_id)
        out.append(finding)
    return out
