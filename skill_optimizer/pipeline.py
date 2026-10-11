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
from skill_optimizer.reporting import write_all_reports, write_json
from skill_optimizer.semantic_analyzer import (
    analyze_heuristic_semantic,
    build_clusters_for_host,
    load_host_semantic_findings,
)
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


def analyze_static_phase(
    cfg: OptimizerConfig,
    *,
    skills: list[SkillRecord] | None = None,
) -> tuple[list[SkillRecord], list[Finding], list[dict[str, Any]], dict[str, Any]]:
    """Deterministic discovery + static + heuristic semantic (no host LLM file)."""
    skills = skills if skills is not None else load_skills(cfg)
    static_findings = analyze_static(skills, cfg)
    heuristic = analyze_heuristic_semantic(skills, cfg)
    findings = _dedupe_findings(static_findings + heuristic)
    clusters = build_clusters_for_host(skills, findings)
    graph = build_conflict_graph(skills, findings, cfg)
    return skills, findings, clusters, graph


def analyze_merge_phase(
    cfg: OptimizerConfig,
    *,
    skills: list[SkillRecord],
    static_findings: list[Finding],
    host_findings: list[Finding],
) -> tuple[list[Finding], dict[str, Any], OptimizationPlan]:
    findings = _dedupe_findings(static_findings + host_findings)
    graph = build_conflict_graph(skills, findings, cfg)
    plan = build_plan(skills, findings, cfg)
    return findings, graph, plan


def analyze(
    cfg: OptimizerConfig,
    *,
    skills: list[SkillRecord] | None = None,
    semantic_findings_path: Path | None = None,
) -> tuple[list[SkillRecord], list[Finding], dict[str, Any], OptimizationPlan]:
    """Full analyze: static/heuristic + optional host semantic-findings.json."""
    skills, static_findings, _clusters, _graph = analyze_static_phase(cfg, skills=skills)
    host: list[Finding] = []
    if semantic_findings_path is not None:
        host = load_host_semantic_findings(semantic_findings_path, skills)
    findings, graph, plan = analyze_merge_phase(
        cfg, skills=skills, static_findings=static_findings, host_findings=host
    )
    return skills, findings, graph, plan


def run_audit_static(cfg: OptimizerConfig, output_dir: Path) -> dict[str, Any]:
    """Phase static: write inventory, static findings, clusters; no final plan merge."""
    skills, findings, clusters, graph = analyze_static_phase(cfg)
    output_dir.mkdir(parents=True, exist_ok=True)
    from skill_optimizer.reporting import write_inventory

    write_inventory(output_dir / "inventory.json", skills)
    write_json(
        output_dir / "findings.static.json",
        {"count": len(findings), "findings": [f.to_dict() for f in findings]},
    )
    write_json(output_dir / "clusters.json", {"count": len(clusters), "clusters": clusters})
    write_json(output_dir / "skill-graph.partial.json", graph)
    # Also write a provisional plan from heuristics alone so audit is useful without host pass
    plan = build_plan(skills, findings, cfg)
    validation_results, metrics = run_validation(skills, findings, cfg, plan=plan)
    paths = write_all_reports(
        output_dir,
        skills=skills,
        findings=findings,
        graph=graph,
        plan=plan,
        validation_results=validation_results,
        metrics=metrics,
        next_step=(
            "Host agent: review clusters.json using references/semantic-review.md, "
            "write semantic-findings.json, then run: audit --phase merge"
        ),
    )
    paths["clusters"] = output_dir / "clusters.json"
    paths["findings_static"] = output_dir / "findings.static.json"
    return {
        "skills": skills,
        "findings": findings,
        "clusters": clusters,
        "graph": graph,
        "plan": plan,
        "validation": validation_results,
        "metrics": metrics,
        "phase": "static",
        "paths": {k: str(v) for k, v in paths.items()},
    }


def run_audit_merge(
    cfg: OptimizerConfig,
    output_dir: Path,
    *,
    semantic_findings_path: Path | None = None,
) -> dict[str, Any]:
    """Phase merge: combine static heuristics with host semantic-findings.json."""
    skills = load_skills(cfg)
    static_path = output_dir / "findings.static.json"
    static_findings: list[Finding] = []
    if static_path.exists():
        static_findings = _findings_from_json(static_path)
    else:
        _, static_findings, _, _ = analyze_static_phase(cfg, skills=skills)

    sem_path = semantic_findings_path or (output_dir / "semantic-findings.json")
    host = load_host_semantic_findings(sem_path, skills)
    findings, graph, plan = analyze_merge_phase(
        cfg, skills=skills, static_findings=static_findings, host_findings=host
    )
    validation_results, metrics = run_validation(skills, findings, cfg, plan=plan)
    paths = write_all_reports(
        output_dir,
        skills=skills,
        findings=findings,
        graph=graph,
        plan=plan,
        validation_results=validation_results,
        metrics=metrics,
        next_step="Review Top actions in audit-report.md; apply only after user confirmation.",
    )
    write_json(
        output_dir / "findings.json",
        {
            "count": len(findings),
            "host_semantic_count": len(host),
            "findings": [f.to_dict() for f in findings],
        },
    )
    return {
        "skills": skills,
        "findings": findings,
        "graph": graph,
        "plan": plan,
        "validation": validation_results,
        "metrics": metrics,
        "phase": "merge",
        "host_findings": host,
        "paths": {k: str(v) for k, v in paths.items()},
    }


def run_audit(
    cfg: OptimizerConfig,
    output_dir: Path,
    *,
    phase: str = "static",
    semantic_findings_path: Path | None = None,
) -> dict[str, Any]:
    if phase == "merge":
        return run_audit_merge(cfg, output_dir, semantic_findings_path=semantic_findings_path)
    if phase == "full":
        # Convenience: static then merge if semantic file present
        result = run_audit_static(cfg, output_dir)
        sem = semantic_findings_path or (output_dir / "semantic-findings.json")
        if sem.exists():
            return run_audit_merge(cfg, output_dir, semantic_findings_path=sem)
        return result
    return run_audit_static(cfg, output_dir)


def run_plan(
    cfg: OptimizerConfig,
    output_dir: Path,
    *,
    semantic_findings_path: Path | None = None,
) -> dict[str, Any]:
    """Plan emphasizes merge when semantic findings exist; else static."""
    sem = semantic_findings_path or (output_dir / "semantic-findings.json")
    if sem.exists():
        return run_audit_merge(cfg, output_dir, semantic_findings_path=sem)
    return run_audit_static(cfg, output_dir)


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
    record = build_skill_record(
        discovery,
        injection_patterns=list(cfg.security.get("injection_patterns", [])),
        related_context_files=[],
    )
    others = [s for s in load_skills(cfg) if s.path != skill_dir]
    skills = others + [record]
    static_findings = analyze_static([record], cfg)
    heuristic = [
        f
        for f in analyze_heuristic_semantic(skills, cfg)
        if record.skill_id in f.skill_ids or len(f.skill_ids) == 1
    ]
    findings = _dedupe_findings(static_findings + heuristic)
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


def _findings_from_json(path: Path) -> list[Finding]:
    import json

    from skill_optimizer.models import Evidence, RelationType, Severity

    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[Finding] = []
    for item in data.get("findings", []):
        evidence = [
            Evidence(
                kind=str(e.get("kind", "")),
                detail=str(e.get("detail", "")),
                files=list(e.get("files") or []),
                metrics=dict(e.get("metrics") or {}),
            )
            for e in item.get("evidence") or []
            if isinstance(e, dict)
        ]
        out.append(
            Finding(
                finding_id=item["finding_id"],
                relation=RelationType(item["relation"]),
                severity=Severity(item["severity"]),
                confidence=float(item.get("confidence", 0.5)),
                skill_ids=list(item.get("skill_ids") or []),
                title=item.get("title", ""),
                summary=item.get("summary", ""),
                evidence=evidence,
                false_positive_risk=str(item.get("false_positive_risk", "low")),
            )
        )
    return out
