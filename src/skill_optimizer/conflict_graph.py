"""Conflict / relationship graph construction."""

from __future__ import annotations

import logging
from typing import Any

from skill_optimizer.config import OptimizerConfig
from skill_optimizer.models import Finding, GraphEdge, RelationType, SkillRecord, severity_rank

logger = logging.getLogger(__name__)


def build_conflict_graph(
    skills: list[SkillRecord],
    findings: list[Finding],
    cfg: OptimizerConfig,
) -> dict[str, Any]:
    weights = cfg.weights
    edges: list[GraphEdge] = []
    for finding in findings:
        if len(finding.skill_ids) < 2:
            # Structural single-node findings become self-edges for reporting.
            if finding.skill_ids:
                edges.append(
                    GraphEdge(
                        source=finding.skill_ids[0],
                        target=finding.skill_ids[0],
                        relation=finding.relation,
                        weight=_edge_weight(finding, weights),
                        finding_id=finding.finding_id,
                        evidence=finding.evidence,
                    )
                )
            continue
        # Fully connect members for multi-skill findings
        for i, src in enumerate(finding.skill_ids):
            for tgt in finding.skill_ids[i + 1 :]:
                edges.append(
                    GraphEdge(
                        source=src,
                        target=tgt,
                        relation=finding.relation,
                        weight=_edge_weight(finding, weights),
                        finding_id=finding.finding_id,
                        evidence=finding.evidence,
                    )
                )

    nodes = [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "platform": s.platform.value,
            "scope": s.scope.value,
            "editable": s.editable,
            "path": str(s.path),
        }
        for s in skills
    ]
    prioritized = sorted(
        findings,
        key=lambda f: (-severity_rank(f.severity), -f.confidence, f.finding_id),
    )
    graph = {
        "nodes": nodes,
        "edges": [e.to_dict() for e in edges],
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "finding_count": len(findings),
            "by_relation": _count_relations(findings),
        },
        "prioritized_finding_ids": [f.finding_id for f in prioritized],
    }
    logger.info(
        "Conflict graph: %d nodes, %d edges, %d findings",
        len(nodes),
        len(edges),
        len(findings),
    )
    return graph


def _edge_weight(finding: Finding, weights: dict[str, float]) -> float:
    mapping = {
        RelationType.DUPLICATE: weights.get("exact_duplicate", 1.0),
        RelationType.CONFLICTS: weights.get("conflict", 0.9),
        RelationType.OVERLAPS: weights.get("overlap", 0.7),
        RelationType.SHADOWS: weights.get("shadow", 0.65),
        RelationType.POTENTIAL_MERGE: weights.get("merge_candidate", 0.55),
        RelationType.COMPLEMENTS: weights.get("complement", 0.2),
        RelationType.DEPENDS_ON: 0.4,
    }
    base = mapping.get(finding.relation, 0.5)
    return base * finding.confidence


def _count_relations(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        key = finding.relation.value
        counts[key] = counts.get(key, 0) + 1
    return counts
