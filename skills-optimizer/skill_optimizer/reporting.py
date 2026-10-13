"""Report writers for audit / plan / validation artifacts."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from skill_optimizer.models import (
    Finding,
    MetricsSnapshot,
    OptimizationPlan,
    SkillRecord,
    ValidationResult,
    severity_rank,
)
from skill_optimizer.planner import top_actions

logger = logging.getLogger(__name__)


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_inventory(path: Path, skills: list[SkillRecord]) -> None:
    payload = {
        "count": len(skills),
        "skills": [s.to_inventory_dict() for s in skills],
    }
    write_json(path, payload)


def write_findings(path: Path, findings: list[Finding]) -> None:
    write_json(path, {"count": len(findings), "findings": [f.to_dict() for f in findings]})


def write_plan(path: Path, plan: OptimizationPlan) -> None:
    write_json(path, plan.to_dict())


def write_validation(
    path: Path,
    results: list[ValidationResult],
    metrics: MetricsSnapshot,
) -> None:
    write_json(
        path,
        {
            "results": [r.to_dict() for r in results],
            "metrics": metrics.to_dict(),
        },
    )


def render_audit_report_md(
    skills: list[SkillRecord],
    findings: list[Finding],
    plan: OptimizationPlan,
    metrics: MetricsSnapshot,
    *,
    next_step: str | None = None,
    findings_limit: int = 40,
    include_inventory: bool = True,
) -> str:
    """Собрать markdown-отчёт (то, что уходит в stdout/чат и в файл)."""
    actions = top_actions(plan, limit=10)
    filtered = max(0, len(findings) - len(actions))
    lines: list[str] = []
    lines.append("# Skill Optimizer Audit Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Skills inventoried: **{len(skills)}**")
    lines.append(f"- Findings: **{len(findings)}**")
    lines.append(f"- Recommendations: **{len(plan.recommendations)}**")
    lines.append(f"- Top actions shown: **{len(actions)}** (other signal compressed: {filtered})")
    lines.append(f"- Plan ID: `{plan.plan_id}`")
    if next_step:
        lines.append(f"- Next step: {next_step}")
    lines.append("")
    lines.append("## Top actions")
    lines.append("")
    if not actions:
        lines.append("No actionable changes recommended.")
    for i, rec in enumerate(actions, 1):
        lines.append(f"{i}. `{rec.operation.value}` - {rec.rationale[:200]}")
        lines.append(f"   - id: `{rec.recommendation_id}`")
        lines.append(f"   - skills: {', '.join(rec.skill_ids)}")
        lines.append(f"   - benefit: {rec.expected_benefit}")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value | Notes |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| routing_accuracy | {_fmt(metrics.routing_accuracy)} | "
        f"{'measured' if metrics.routing_accuracy is not None else 'not measured'} |"
    )
    lines.append(
        f"| false_activation_rate | {_fmt(metrics.false_activation_rate)} | "
        f"{'measured' if metrics.false_activation_rate is not None else 'not measured'} |"
    )
    lines.append(
        f"| capability_retention | {_fmt(metrics.capability_retention)} | "
        f"{'measured' if metrics.capability_retention is not None else 'not measured'} |"
    )
    lines.append(f"| structural_validity | {metrics.structural_validity:.3f} | measured |")
    lines.append(f"| unresolved_conflicts | {metrics.unresolved_conflicts} | measured |")
    lines.append(f"| context_cost_tokens | {metrics.context_cost_tokens} | estimated |")
    for note in metrics.notes:
        lines.append(f"| note |  | {note} |")
    lines.append("")
    lines.append("## Findings (priority order)")
    lines.append("")
    ordered = sorted(
        findings,
        key=lambda f: (-severity_rank(f.severity), -f.confidence, f.finding_id),
    )
    if not ordered:
        lines.append("No findings.")
    for finding in ordered[:findings_limit]:
        lines.append(
            f"### {finding.severity.value.upper()} - {finding.title} (`{finding.finding_id}`)"
        )
        lines.append("")
        lines.append(f"- Relation: `{finding.relation.value}`")
        lines.append(f"- Confidence: {finding.confidence:.2f}")
        lines.append(f"- Skills: {', '.join(finding.skill_ids)}")
        lines.append(f"- Summary: {finding.summary}")
        if finding.evidence:
            lines.append("- Evidence:")
            for ev in finding.evidence[:5]:
                lines.append(f"  - {ev.kind}: {ev.detail}")
        lines.append("")
    if len(ordered) > findings_limit:
        lines.append(f"_… {len(ordered) - findings_limit} more findings in findings.json_")
        lines.append("")
    lines.append("## Optimization plan")
    lines.append("")
    for rec in plan.recommendations:
        lines.append(f"### {rec.operation.value} - `{rec.recommendation_id}`")
        lines.append("")
        lines.append(f"- Priority: {rec.priority}")
        lines.append(f"- Skills: {', '.join(rec.skill_ids)}")
        lines.append(f"- Rationale: {rec.rationale}")
        lines.append(f"- Expected benefit: {rec.expected_benefit}")
        if rec.risks:
            lines.append(f"- Risks: {'; '.join(rec.risks)}")
        lines.append("- Verification:")
        for crit in rec.verification_criteria:
            lines.append(f"  - {crit}")
        lines.append("")
    if include_inventory:
        lines.append("## Inventory")
        lines.append("")
        for skill in skills:
            lines.append(
                f"- `{skill.name}` [{skill.platform.value}/{skill.scope.value}] "
                f"editable={skill.editable} path=`{skill.path}`"
            )
        lines.append("")
    return "\n".join(lines)


def render_chat_report_md(
    skills: list[SkillRecord],
    findings: list[Finding],
    plan: OptimizationPlan,
    metrics: MetricsSnapshot,
    *,
    next_step: str | None = None,
) -> str:
    """Короткий отчёт для чата: Summary + Top actions + Metrics (без полного inventory)."""
    return render_audit_report_md(
        skills,
        findings,
        plan,
        metrics,
        next_step=next_step,
        findings_limit=15,
        include_inventory=False,
    )


def write_audit_report_md(
    path: Path,
    skills: list[SkillRecord],
    findings: list[Finding],
    plan: OptimizationPlan,
    metrics: MetricsSnapshot,
    *,
    next_step: str | None = None,
) -> str:
    text = render_audit_report_md(
        skills, findings, plan, metrics, next_step=next_step
    )
    path.write_text(text, encoding="utf-8")
    logger.info("Wrote audit report %s", path)
    return text


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def write_all_reports(
    output_dir: Path,
    *,
    skills: list[SkillRecord],
    findings: list[Finding],
    graph: dict[str, Any],
    plan: OptimizationPlan,
    validation_results: list[ValidationResult],
    metrics: MetricsSnapshot,
    next_step: str | None = None,
) -> tuple[dict[str, Path], str]:
    """Пишет артефакты на диск и возвращает (paths, chat_report_md)."""
    ensure_output_dir(output_dir)
    paths = {
        "inventory": output_dir / "inventory.json",
        "findings": output_dir / "findings.json",
        "graph": output_dir / "skill-graph.json",
        "plan": output_dir / "optimization-plan.json",
        "audit": output_dir / "audit-report.md",
        "validation": output_dir / "validation-report.json",
    }
    write_inventory(paths["inventory"], skills)
    write_findings(paths["findings"], findings)
    write_json(paths["graph"], graph)
    write_plan(paths["plan"], plan)
    write_validation(paths["validation"], validation_results, metrics)
    write_audit_report_md(
        paths["audit"], skills, findings, plan, metrics, next_step=next_step
    )
    chat_md = render_chat_report_md(
        skills, findings, plan, metrics, next_step=next_step
    )
    return paths, chat_md
