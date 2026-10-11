"""Heuristic semantic analysis + host-LLM finding merge helpers.

Deep semantic judgment is performed by the host agent (the LLM running the skill),
which writes semantic-findings.json. This module provides deterministic heuristics
and utilities to load/validate host findings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from skill_optimizer.config import OptimizerConfig
from skill_optimizer.models import (
    Evidence,
    Finding,
    RelationType,
    Severity,
    SkillRecord,
)
from skill_optimizer.textutil import (
    contradiction_pairs,
    jaccard,
    token_set,
)

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFO,
}


def analyze_heuristic_semantic(
    skills: list[SkillRecord],
    cfg: OptimizerConfig,
) -> list[Finding]:
    """Baseline semantic heuristics (no external LLM API)."""
    findings: list[Finding] = []
    findings.extend(_capability_overlaps(skills, cfg))
    findings.extend(_scope_shadows(skills))
    findings.extend(_instruction_conflicts(skills))
    findings.extend(_complements(skills))
    findings.extend(_multi_skill_clusters(skills, cfg))
    logger.info("Heuristic semantic analyzer produced %d findings", len(findings))
    return findings


# Backward-compatible alias used by older call sites/tests
def analyze_semantic(
    skills: list[SkillRecord],
    cfg: OptimizerConfig,
    provider: Any = None,
) -> list[Finding]:
    del provider
    return analyze_heuristic_semantic(skills, cfg)


def build_clusters_for_host(
    skills: list[SkillRecord],
    findings: list[Finding],
) -> list[dict[str, Any]]:
    """Build compact cluster payloads for host-LLM semantic review."""
    by_id = {s.skill_id: s for s in skills}
    clusters: list[dict[str, Any]] = []
    used: set[str] = set()

    # Multi-skill findings first
    for finding in findings:
        if len(finding.skill_ids) < 2:
            continue
        key = tuple(sorted(finding.skill_ids))
        key_s = "|".join(key)
        if key_s in used:
            continue
        used.add(key_s)
        members = []
        for sid in finding.skill_ids:
            skill = by_id.get(sid)
            if not skill:
                continue
            members.append(_skill_brief(skill))
        if len(members) < 2:
            continue
        clusters.append(
            {
                "cluster_id": f"cluster-{len(clusters)+1:03d}",
                "reason": finding.relation.value,
                "seed_finding_id": finding.finding_id,
                "skills": members,
            }
        )

    # Solo structural / injection cases worth host review
    for finding in findings:
        if len(finding.skill_ids) != 1:
            continue
        if finding.severity not in {Severity.CRITICAL, Severity.HIGH}:
            continue
        sid = finding.skill_ids[0]
        skill = by_id.get(sid)
        if not skill:
            continue
        clusters.append(
            {
                "cluster_id": f"solo-{len(clusters)+1:03d}",
                "reason": finding.relation.value,
                "seed_finding_id": finding.finding_id,
                "skills": [_skill_brief(skill)],
            }
        )
    return clusters


def _skill_brief(skill: SkillRecord) -> dict[str, Any]:
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "path": str(skill.path),
        "skill_md_path": str(skill.skill_md_path),
        "scope": skill.scope.value,
        "platform": skill.platform.value,
        "description": skill.description,
        "capabilities": skill.capabilities[:20],
        "triggers": skill.triggers[:20],
        "exclusions": skill.exclusions[:20],
        "body_excerpt": (skill.body or "")[:1200],
        "structural_issues": skill.structural_issues,
        "injection_flags": skill.injection_flags,
    }


def load_host_semantic_findings(
    path: Path,
    skills: list[SkillRecord],
) -> list[Finding]:
    """Load semantic-findings.json produced by the host agent."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load host semantic findings %s: %s", path, exc)
        return []

    known = {s.skill_id for s in skills}
    name_to_ids: dict[str, list[str]] = {}
    for s in skills:
        name_to_ids.setdefault(s.name, []).append(s.skill_id)

    raw_findings = data.get("findings", data if isinstance(data, list) else [])
    out: list[Finding] = []
    for i, item in enumerate(raw_findings):
        if not isinstance(item, dict):
            continue
        skill_ids = list(item.get("skill_ids") or [])
        # Allow host to reference by name
        if not skill_ids and item.get("skill_names"):
            for name in item["skill_names"]:
                skill_ids.extend(name_to_ids.get(name, []))
        skill_ids = [sid for sid in skill_ids if sid in known]
        if not skill_ids and item.get("skill_names"):
            # Keep unresolved names as empty — skip
            logger.warning("Host finding skipped; unknown skills: %s", item.get("skill_names"))
            continue
        try:
            relation = RelationType(str(item.get("relation", "OVERLAPS")))
        except ValueError:
            relation = RelationType.OVERLAPS
        severity = _SEVERITY_MAP.get(str(item.get("severity", "medium")).lower(), Severity.MEDIUM)
        evidence = []
        for ev in item.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            evidence.append(
                Evidence(
                    kind=str(ev.get("kind", "host_llm")),
                    detail=str(ev.get("detail", "")),
                    files=list(ev.get("files") or []),
                    metrics=dict(ev.get("metrics") or {}),
                )
            )
        fid = str(item.get("finding_id") or f"host-{i+1:03d}")
        out.append(
            Finding(
                finding_id=fid if fid.startswith("host-") else f"host-{fid}",
                relation=relation,
                severity=severity,
                confidence=float(item.get("confidence", 0.7)),
                skill_ids=skill_ids,
                title=str(item.get("title") or "Host semantic finding"),
                summary=str(item.get("summary") or ""),
                evidence=evidence
                or [
                    Evidence(
                        kind="host_llm",
                        detail="Provided by host agent semantic review",
                        files=[],
                    )
                ],
                false_positive_risk=str(item.get("false_positive_risk", "medium")),
            )
        )
    logger.info("Loaded %d host semantic findings from %s", len(out), path)
    return out


def _capability_overlaps(skills: list[SkillRecord], cfg: OptimizerConfig) -> list[Finding]:
    cap_min = float(cfg.thresholds.get("capability_overlap_min", 0.5))
    trig_min = float(cfg.thresholds.get("trigger_overlap_min", 0.4))
    findings: list[Finding] = []
    for i, a in enumerate(skills):
        a_caps = token_set(" ".join(a.capabilities))
        a_trigs = token_set(" ".join(a.triggers))
        for b in skills[i + 1 :]:
            if a.content_sha256 == b.content_sha256:
                continue
            b_caps = token_set(" ".join(b.capabilities))
            b_trigs = token_set(" ".join(b.triggers))
            cap_score = jaccard(a_caps, b_caps)
            trig_score = jaccard(a_trigs, b_trigs)
            if cap_score < cap_min and trig_score < trig_min:
                continue

            specialization = _looks_like_specialization(a, b)
            if specialization and cap_score < 0.85:
                findings.append(
                    Finding(
                        finding_id=f"comp-{a.content_sha256[:6]}-{b.content_sha256[:6]}",
                        relation=RelationType.COMPLEMENTS,
                        severity=Severity.INFO,
                        confidence=0.65,
                        skill_ids=[a.skill_id, b.skill_id],
                        title="Related skills with distinct specialization",
                        summary=(
                            f"{a.name} and {b.name} share themes but exclusions/capabilities "
                            "indicate useful specialization rather than harmful duplication."
                        ),
                        evidence=[
                            Evidence(
                                kind="specialization",
                                detail="Distinct exclusions or capability focus",
                                files=[str(a.skill_md_path), str(b.skill_md_path)],
                                metrics={
                                    "capability_jaccard": round(cap_score, 4),
                                    "trigger_jaccard": round(trig_score, 4),
                                },
                            )
                        ],
                        false_positive_risk="low",
                    )
                )
                continue

            relation = RelationType.OVERLAPS
            severity = Severity.MEDIUM
            if cap_score >= 0.8 and trig_score >= 0.7:
                relation = RelationType.POTENTIAL_MERGE
                severity = Severity.HIGH
            findings.append(
                Finding(
                    finding_id=f"overlap-{a.content_sha256[:6]}-{b.content_sha256[:6]}",
                    relation=relation,
                    severity=severity,
                    confidence=min(0.95, 0.5 + 0.5 * max(cap_score, trig_score)),
                    skill_ids=[a.skill_id, b.skill_id],
                    title=f"Functional overlap: {a.name} ↔ {b.name}",
                    summary=(
                        f"Capability Jaccard={cap_score:.2f}, trigger Jaccard={trig_score:.2f}."
                    ),
                    evidence=[
                        Evidence(
                            kind="capability_overlap",
                            detail="Shared capability/trigger tokens",
                            files=[str(a.skill_md_path), str(b.skill_md_path)],
                            metrics={
                                "capability_jaccard": round(cap_score, 4),
                                "trigger_jaccard": round(trig_score, 4),
                            },
                        )
                    ],
                )
            )
    return findings


def _looks_like_specialization(a: SkillRecord, b: SkillRecord) -> bool:
    if a.exclusions or b.exclusions:
        a_excl = token_set(" ".join(a.exclusions))
        b_trig = token_set(" ".join(b.triggers + b.capabilities))
        b_excl = token_set(" ".join(b.exclusions))
        a_trig = token_set(" ".join(a.triggers + a.capabilities))
        if len(a_excl & b_trig) >= 2 or len(b_excl & a_trig) >= 2:
            return True
    if a.name != b.name and a.name.split("-")[0] != b.name.split("-")[0]:
        shared = token_set(a.description) & token_set(b.description)
        if len(shared) <= 5:
            return True
    return False


def _scope_shadows(skills: list[SkillRecord]) -> list[Finding]:
    by_name: dict[str, list[SkillRecord]] = {}
    for skill in skills:
        by_name.setdefault(skill.name, []).append(skill)
    findings: list[Finding] = []
    for name, group in by_name.items():
        scopes = {s.scope.value for s in group}
        if "user" in scopes and "project" in scopes:
            user = [s for s in group if s.scope.value == "user"]
            project = [s for s in group if s.scope.value == "project"]
            findings.append(
                Finding(
                    finding_id=f"shadow-{name}",
                    relation=RelationType.SHADOWS,
                    severity=Severity.HIGH,
                    confidence=0.9,
                    skill_ids=[s.skill_id for s in group],
                    title=f"User/project scope shadow for {name}",
                    summary=(
                        f"Skill name {name!r} exists in both user and project scopes. "
                        "Routing may prefer one and hide the other."
                    ),
                    evidence=[
                        Evidence(
                            kind="scope_shadow",
                            detail="Same skill name across scopes",
                            files=[str(s.skill_md_path) for s in user + project],
                            metrics={"user_count": len(user), "project_count": len(project)},
                        )
                    ],
                )
            )
    return findings


def _instruction_conflicts(skills: list[SkillRecord]) -> list[Finding]:
    findings: list[Finding] = []
    for i, a in enumerate(skills):
        for b in skills[i + 1 :]:
            pairs = contradiction_pairs(a.exclusions, b.capabilities + b.triggers)
            pairs += contradiction_pairs(b.exclusions, a.capabilities + a.triggers)
            opposing = _opposing_imperatives(a.body, b.body)
            if not pairs and not opposing:
                continue
            evidence = [
                Evidence(
                    kind="contradiction",
                    detail=f"Exclusion vs capability: {excl} || {cap}",
                    files=[str(a.skill_md_path), str(b.skill_md_path)],
                )
                for excl, cap in pairs[:5]
            ]
            evidence.extend(
                Evidence(
                    kind="opposing_imperative",
                    detail=detail,
                    files=[str(a.skill_md_path), str(b.skill_md_path)],
                )
                for detail in opposing[:5]
            )
            findings.append(
                Finding(
                    finding_id=f"conflict-{a.content_sha256[:6]}-{b.content_sha256[:6]}",
                    relation=RelationType.CONFLICTS,
                    severity=Severity.HIGH,
                    confidence=0.75 if pairs else 0.6,
                    skill_ids=[a.skill_id, b.skill_id],
                    title=f"Contradictory instructions: {a.name} ↔ {b.name}",
                    summary="Detected exclusion/capability or opposing imperative guidance.",
                    evidence=evidence,
                )
            )
    return findings


def _opposing_imperatives(body_a: str, body_b: str) -> list[str]:
    positives = []
    negatives = []
    for source, bucket, polarity in (
        (body_a, positives, True),
        (body_a, negatives, False),
        (body_b, positives, True),
        (body_b, negatives, False),
    ):
        for line in source.splitlines():
            low = line.lower().strip()
            if not low:
                continue
            if polarity and any(low.startswith(p) for p in ("always ", "you must ", "do ")):
                bucket.append(low)
            if not polarity and any(
                x in low for x in ("never ", "do not ", "don't ", "avoid ")
            ):
                bucket.append(low)
    details: list[str] = []
    for pos in positives:
        pos_tokens = token_set(pos) - {"always", "must", "you", "do"}
        for neg in negatives:
            neg_tokens = token_set(neg) - {"never", "do", "not", "dont", "avoid", "you"}
            if len(pos_tokens & neg_tokens) >= 2:
                details.append(f"{pos[:120]} <-> {neg[:120]}")
    return details


def _complements(skills: list[SkillRecord]) -> list[Finding]:
    findings: list[Finding] = []
    names = {s.name: s for s in skills}
    for skill in skills:
        text = f"{skill.description}\n{skill.body}".lower()
        for other_name, other in names.items():
            if other.skill_id == skill.skill_id:
                continue
            if f"depends on {other_name}" in text or f"requires `{other_name}`" in text:
                findings.append(
                    Finding(
                        finding_id=f"dep-{skill.content_sha256[:6]}-{other.content_sha256[:6]}",
                        relation=RelationType.DEPENDS_ON,
                        severity=Severity.INFO,
                        confidence=0.8,
                        skill_ids=[skill.skill_id, other.skill_id],
                        title=f"{skill.name} depends on {other_name}",
                        summary="Explicit dependency reference found in instructions.",
                        evidence=[
                            Evidence(
                                kind="depends_on",
                                detail=f"Reference to {other_name}",
                                files=[str(skill.skill_md_path)],
                            )
                        ],
                    )
                )
    return findings


def _multi_skill_clusters(skills: list[SkillRecord], cfg: OptimizerConfig) -> list[Finding]:
    cap_min = float(cfg.thresholds.get("capability_overlap_min", 0.5))
    ids = [s.skill_id for s in skills]
    index = {s.skill_id: s for s in skills}
    adj: dict[str, set[str]] = {i: set() for i in ids}
    for i, a in enumerate(skills):
        for b in skills[i + 1 :]:
            score = jaccard(
                token_set(" ".join(a.capabilities + a.triggers)),
                token_set(" ".join(b.capabilities + b.triggers)),
            )
            if score >= cap_min:
                adj[a.skill_id].add(b.skill_id)
                adj[b.skill_id].add(a.skill_id)

    visited: set[str] = set()
    findings: list[Finding] = []
    for start in ids:
        if start in visited:
            continue
        stack = [start]
        component: list[str] = []
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            stack.extend(adj[node] - visited)
        if len(component) < 3:
            continue
        names = [index[i].name for i in component]
        findings.append(
            Finding(
                finding_id=f"cluster-{hash(tuple(sorted(component))) & 0xFFFFFFFF:x}",
                relation=RelationType.OVERLAPS,
                severity=Severity.HIGH,
                confidence=0.7,
                skill_ids=component,
                title=f"Multi-skill overlap cluster ({len(component)})",
                summary="Skills with pairwise capability/trigger overlap: " + ", ".join(names),
                evidence=[
                    Evidence(
                        kind="cluster",
                        detail="Connected component in overlap graph",
                        files=[str(index[i].skill_md_path) for i in component],
                        metrics={"size": len(component)},
                    )
                ],
            )
        )
    return findings
