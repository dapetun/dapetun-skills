"""Optimization planner: actionable recommendations from findings."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from skill_optimizer.config import OptimizerConfig
from skill_optimizer.models import (
    Finding,
    OperationType,
    OptimizationPlan,
    Recommendation,
    RelationType,
    Severity,
    SkillRecord,
    severity_rank,
)

logger = logging.getLogger(__name__)

_SEVERITY_FLOOR = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}


def build_plan(
    skills: list[SkillRecord],
    findings: list[Finding],
    cfg: OptimizerConfig,
) -> OptimizationPlan:
    by_id = {s.skill_id: s for s in skills}
    min_conf = float(cfg.thresholds.get("min_confidence_report", 0.45))
    min_sev = _SEVERITY_FLOOR.get(str(cfg.min_severity).lower(), 3)

    actionable = [
        f
        for f in findings
        if f.confidence >= min_conf
        and f.relation not in {RelationType.COMPLEMENTS, RelationType.DEPENDS_ON}
    ]
    clustered_findings = _cluster_findings(actionable)

    recommendations: list[Recommendation] = []
    used_ops: set[tuple[str, tuple[str, ...]]] = set()
    ordered = sorted(
        clustered_findings,
        key=lambda f: (-severity_rank(f.severity), -f.confidence, f.finding_id),
    )
    for finding in ordered:
        rec = _recommendation_for_finding(finding, by_id)
        if rec is None:
            continue
        if rec.operation in {OperationType.NO_CHANGE}:
            continue
        if severity_rank(finding.severity) < min_sev and finding.relation != RelationType.DUPLICATE:
            # Keep critical duplicates even if filter is high; otherwise respect floor
            continue
        key = (rec.operation.value, tuple(sorted(rec.skill_ids)))
        if key in used_ops:
            continue
        used_ops.add(key)
        recommendations.append(rec)

    if not recommendations:
        recommendations.append(
            Recommendation(
                recommendation_id=f"rec-{uuid.uuid4().hex[:10]}",
                operation=OperationType.NO_CHANGE,
                skill_ids=[s.skill_id for s in skills],
                rationale="No actionable issues above confidence/severity thresholds.",
                expected_benefit="Preserve current skill ecosystem coherence.",
                risks=["Missing a subtle conflict that heuristics/host review did not detect."],
                verification_criteria=[
                    "Re-run audit after adding/editing skills",
                    "Confirm routing on representative prompts still matches intent",
                ],
                priority=100,
                requires_confirmation=False,
            )
        )

    plan = OptimizationPlan(
        plan_id=f"plan-{uuid.uuid4().hex[:12]}",
        created_at=datetime.now(timezone.utc).isoformat(),
        skill_hashes={s.skill_id: s.content_sha256 for s in skills},
        recommendations=recommendations,
        notes=[
            "Do not merge skills based solely on textual similarity.",
            "Read-only by default; apply requires explicit confirmation.",
            "Third-party/builtin skills are never modified.",
            "Deep semantic judgment comes from the host agent via semantic-findings.json.",
            f"Recommendations clustered; min_severity={cfg.min_severity}.",
        ],
    )
    logger.info("Optimization plan %s with %d recommendations", plan.plan_id, len(recommendations))
    return plan


def _cluster_findings(findings: list[Finding]) -> list[Finding]:
    """Collapse pairwise overlap/conflict findings into connected components."""
    multi_rels = {
        RelationType.OVERLAPS,
        RelationType.POTENTIAL_MERGE,
        RelationType.CONFLICTS,
        RelationType.SHADOWS,
        RelationType.DUPLICATE,
    }
    multi = [f for f in findings if len(f.skill_ids) >= 2 and f.relation in multi_rels]
    solo = [f for f in findings if len(f.skill_ids) < 2]

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for finding in multi:
        ids = finding.skill_ids
        for i in range(1, len(ids)):
            union(ids[0], ids[i])

    groups: dict[str, list[Finding]] = {}
    for finding in multi:
        root = find(finding.skill_ids[0])
        groups.setdefault(root, []).append(finding)

    representatives: list[Finding] = []
    for group in groups.values():
        best = max(
            group,
            key=lambda f: (severity_rank(f.severity), f.confidence),
        )
        # Expand skill_ids to full component
        member_ids: set[str] = set()
        for f in group:
            member_ids.update(f.skill_ids)
        representatives.append(
            Finding(
                finding_id=best.finding_id,
                relation=best.relation,
                severity=best.severity,
                confidence=best.confidence,
                skill_ids=sorted(member_ids),
                title=best.title
                if len(member_ids) <= 2
                else f"Cluster issue ({len(member_ids)} skills): {best.title}",
                summary=best.summary,
                evidence=best.evidence,
                false_positive_risk=best.false_positive_risk,
            )
        )

    # Solo: keep one per skill_id (highest severity)
    solo_best: dict[str, Finding] = {}
    for finding in solo:
        key = finding.skill_ids[0] if finding.skill_ids else finding.finding_id
        prev = solo_best.get(key)
        if prev is None or severity_rank(finding.severity) > severity_rank(prev.severity):
            solo_best[key] = finding

    return representatives + list(solo_best.values())


def top_actions(plan: OptimizationPlan, limit: int = 10) -> list[Recommendation]:
    actionable = [
        r
        for r in plan.recommendations
        if r.operation
        not in {OperationType.NO_CHANGE}
    ]
    return sorted(actionable, key=lambda r: (r.priority, r.recommendation_id))[:limit]


def _recommendation_for_finding(
    finding: Finding,
    by_id: dict[str, SkillRecord],
) -> Recommendation | None:
    skills = [by_id[i] for i in finding.skill_ids if i in by_id]
    if not skills and finding.relation != RelationType.CONFLICTS:
        return None

    rid = f"rec-{finding.finding_id}"

    if finding.relation == RelationType.DUPLICATE:
        editable = [s for s in skills if s.editable]
        keep = skills[0]
        deprecate = editable[1:] if len(editable) > 1 else editable
        return Recommendation(
            recommendation_id=rid,
            operation=OperationType.DEPRECATE_SKILL if deprecate else OperationType.NO_CHANGE,
            skill_ids=[s.skill_id for s in skills],
            rationale=finding.summary,
            expected_benefit="Remove exact duplicate routing noise while keeping one canonical skill.",
            risks=["Deprecating the wrong copy if scopes intentionally mirror content."],
            verification_criteria=[
                "Exactly one canonical copy remains active for the intended scope",
                "Capabilities from deprecated copies exist in the retained skill",
            ],
            priority=_priority(finding),
            patch_hints={
                "keep_skill_id": keep.skill_id,
                "deprecate_skill_ids": [s.skill_id for s in deprecate],
                "action": "add_deprecation_notice",
            },
        )

    if finding.relation == RelationType.CONFLICTS and len(skills) == 1:
        skill = skills[0] if skills else by_id.get(finding.skill_ids[0]) if finding.skill_ids else None
        if skill and skill.injection_flags:
            return Recommendation(
                recommendation_id=rid,
                operation=OperationType.REWRITE_INSTRUCTIONS,
                skill_ids=finding.skill_ids,
                rationale="Prompt-injection-like markers found in untrusted skill content.",
                expected_benefit="Reduce risk of instruction hijack when agents load the skill.",
                risks=["Legitimate security examples may look like injection patterns."],
                verification_criteria=[
                    "Injection markers removed or clearly quarantined as examples",
                    "Skill still describes the intended workflow",
                ],
                priority=1,
                patch_hints={"injection_flags": skill.injection_flags},
            )
        if skill and skill.broken_links:
            return Recommendation(
                recommendation_id=rid,
                operation=OperationType.FIX_STRUCTURE,
                skill_ids=finding.skill_ids,
                rationale=finding.summary,
                expected_benefit="Repair broken references so progressive disclosure works.",
                risks=["Referenced files may have been intentionally removed."],
                verification_criteria=["All relative links resolve under the skill root"],
                priority=_priority(finding),
                patch_hints={"broken_links": skill.broken_links},
            )
        if skill and (
            skill.frontmatter.parse_error
            or any("Missing required" in i or "Invalid YAML" in i for i in skill.structural_issues)
        ):
            return Recommendation(
                recommendation_id=rid,
                operation=OperationType.FIX_STRUCTURE,
                skill_ids=finding.skill_ids,
                rationale=finding.summary,
                expected_benefit="Restore agentskills.io frontmatter validity and discoverability.",
                risks=["Automated fixes may need manual wording review."],
                verification_criteria=[
                    "SKILL.md parses with valid name/description",
                    "name matches directory name",
                ],
                priority=_priority(finding),
                patch_hints={"issues": [e.detail for e in finding.evidence]},
            )
        return Recommendation(
            recommendation_id=rid,
            operation=OperationType.FIX_STRUCTURE,
            skill_ids=finding.skill_ids,
            rationale=finding.summary,
            expected_benefit="Bring skill in line with Agent Skills specification.",
            risks=["Manual content review still required."],
            verification_criteria=["Structural validator reports no blocking issues"],
            priority=_priority(finding),
        )

    if finding.relation == RelationType.CONFLICTS and len(skills) >= 2:
        return Recommendation(
            recommendation_id=rid,
            operation=OperationType.REWRITE_INSTRUCTIONS,
            skill_ids=finding.skill_ids,
            rationale=finding.summary,
            expected_benefit="Remove contradictory guidance that causes inconsistent agent behavior.",
            risks=["Over-editing may erase intentional policy differences across scopes."],
            verification_criteria=[
                "No opposing always/never guidance on the same subject",
                "Each skill states clear exclusions",
            ],
            priority=_priority(finding),
            patch_hints={"align_exclusions": True},
        )

    if finding.relation == RelationType.SHADOWS and "broad" in finding.finding_id:
        return Recommendation(
            recommendation_id=rid,
            operation=OperationType.REFINE_DESCRIPTION,
            skill_ids=finding.skill_ids,
            rationale=finding.summary,
            expected_benefit="Lower false activation rate by narrowing trigger language.",
            risks=["Over-narrowing may reduce legitimate recalls."],
            verification_criteria=[
                "Description includes both what and when",
                "False-activation probes no longer select this skill",
            ],
            priority=_priority(finding),
        )

    if finding.relation == RelationType.SHADOWS:
        return Recommendation(
            recommendation_id=rid,
            operation=OperationType.CHANGE_SCOPE,
            skill_ids=finding.skill_ids,
            rationale=finding.summary,
            expected_benefit="Clarify which scope is canonical for this skill name.",
            risks=["Removing user copy may surprise personal workflows."],
            verification_criteria=[
                "Only one active skill per intended scope wins routing",
                "Documented ownership of user vs project variant",
            ],
            priority=_priority(finding),
            patch_hints={"prefer_scope": "project"},
        )

    if finding.relation == RelationType.POTENTIAL_MERGE:
        if finding.false_positive_risk == "medium" and finding.confidence < 0.9:
            return Recommendation(
                recommendation_id=rid,
                operation=OperationType.EXTRACT_SHARED_RESOURCE,
                skill_ids=finding.skill_ids,
                rationale=(
                    finding.summary
                    + " Prefer extracting shared references over merging on text similarity alone."
                ),
                expected_benefit="Deduplicate shared instructions without losing specialization.",
                risks=["Shared resources can create hidden coupling."],
                verification_criteria=[
                    "Shared reference file linked from both skills",
                    "Unique capabilities retained in each skill",
                ],
                priority=_priority(finding),
            )
        return Recommendation(
            recommendation_id=rid,
            operation=OperationType.MERGE_SKILLS,
            skill_ids=finding.skill_ids,
            rationale=finding.summary,
            expected_benefit="Consolidate near-identical responsibilities into one skill with preserved resources.",
            risks=[
                "Merge may hide useful specialization",
                "Resource paths must be remapped carefully",
            ],
            verification_criteria=[
                "Union of capabilities retained",
                "All resources from both skills present in merge output",
                "Routing probes for both former skills select the merged skill",
            ],
            priority=_priority(finding),
            patch_hints={"preserve_resources": True},
        )

    if finding.relation == RelationType.OVERLAPS and len(skills) >= 3:
        return Recommendation(
            recommendation_id=rid,
            operation=OperationType.SPLIT_SKILL
            if any(len((s.description or "")) > 800 for s in skills)
            else OperationType.REFINE_DESCRIPTION,
            skill_ids=finding.skill_ids,
            rationale=finding.summary,
            expected_benefit="Clarify boundaries across the overlapping cluster.",
            risks=["Fragmentation can increase routing complexity."],
            verification_criteria=[
                "Each skill has non-overlapping primary triggers",
                "Cluster unresolved-conflict count decreases",
            ],
            priority=_priority(finding),
        )

    if finding.relation == RelationType.OVERLAPS:
        return Recommendation(
            recommendation_id=rid,
            operation=OperationType.REFINE_DESCRIPTION,
            skill_ids=finding.skill_ids,
            rationale=finding.summary,
            expected_benefit="Sharpen ownership boundaries without deleting functionality.",
            risks=["Descriptions may need domain-expert wording."],
            verification_criteria=["Overlap finding confidence drops below threshold on re-audit"],
            priority=_priority(finding),
        )

    return None


def _priority(finding: Finding) -> int:
    base = {
        Severity.CRITICAL: 1,
        Severity.HIGH: 10,
        Severity.MEDIUM: 30,
        Severity.LOW: 50,
        Severity.INFO: 80,
    }[finding.severity]
    return base + int((1.0 - finding.confidence) * 10)


def plan_from_dict(data: dict[str, Any]) -> OptimizationPlan:
    recs = []
    for item in data.get("recommendations", []):
        recs.append(
            Recommendation(
                recommendation_id=item["recommendation_id"],
                operation=OperationType(item["operation"]),
                skill_ids=list(item.get("skill_ids", [])),
                rationale=item.get("rationale", ""),
                expected_benefit=item.get("expected_benefit", ""),
                risks=list(item.get("risks", [])),
                verification_criteria=list(item.get("verification_criteria", [])),
                priority=int(item.get("priority", 50)),
                patch_hints=dict(item.get("patch_hints", {})),
                requires_confirmation=bool(item.get("requires_confirmation", True)),
            )
        )
    return OptimizationPlan(
        plan_id=data["plan_id"],
        created_at=data.get("created_at", ""),
        skill_hashes=dict(data.get("skill_hashes", {})),
        recommendations=recs,
        notes=list(data.get("notes", [])),
    )
