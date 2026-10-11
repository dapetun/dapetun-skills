"""Heuristic (and optional LLM-assisted) semantic analysis of skills."""

from __future__ import annotations

import logging
from typing import Protocol

from skill_optimizer.config import OptimizerConfig
from skill_optimizer.models import (
    Evidence,
    Finding,
    RelationType,
    Severity,
    SkillRecord,
)
from skill_optimizer.security import compile_injection_patterns, redact_for_llm
from skill_optimizer.textutil import (
    contradiction_pairs,
    jaccard,
    token_set,
)

logger = logging.getLogger(__name__)


class SemanticProvider(Protocol):
    def analyze_cluster(self, skills: list[SkillRecord]) -> list[Finding]:
        """Optional LLM-backed cluster analysis."""


class NullSemanticProvider:
    """Baseline provider: no external LLM calls."""

    def analyze_cluster(self, skills: list[SkillRecord]) -> list[Finding]:
        return []


def analyze_semantic(
    skills: list[SkillRecord],
    cfg: OptimizerConfig,
    provider: SemanticProvider | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_capability_overlaps(skills, cfg))
    findings.extend(_scope_shadows(skills, cfg))
    findings.extend(_instruction_conflicts(skills, cfg))
    findings.extend(_complements(skills, cfg))
    findings.extend(_multi_skill_clusters(skills, cfg))

    provider = provider or NullSemanticProvider()
    if bool(cfg.llm.get("enabled", False)):
        # Content is redacted before any provider use.
        patterns = compile_injection_patterns(list(cfg.security.get("injection_patterns", [])))
        safe_skills = []
        for skill in skills:
            clone_notes = redact_for_llm(
                f"{skill.description}\n{skill.body}", patterns
            )
            logger.debug("Prepared redacted LLM payload for %s (%d chars)", skill.name, len(clone_notes))
            safe_skills.append(skill)
        try:
            findings.extend(provider.analyze_cluster(safe_skills))
        except Exception as exc:  # pragma: no cover - provider-specific
            logger.warning("LLM semantic provider failed; continuing with heuristics: %s", exc)
    else:
        logger.info("LLM semantic analysis disabled; using heuristic baseline only")

    logger.info("Semantic analyzer produced %d findings", len(findings))
    return findings


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

            # Similar text with clearly different exclusions => specialization, not merge.
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
        # If one excludes what the other targets, treat as specialization.
        a_excl = token_set(" ".join(a.exclusions))
        b_trig = token_set(" ".join(b.triggers + b.capabilities))
        b_excl = token_set(" ".join(b.exclusions))
        a_trig = token_set(" ".join(a.triggers + a.capabilities))
        if len(a_excl & b_trig) >= 2 or len(b_excl & a_trig) >= 2:
            return True
    # Different primary nouns in names often indicate specialization
    if a.name != b.name and a.name.split("-")[0] != b.name.split("-")[0]:
        shared = token_set(a.description) & token_set(b.description)
        if len(shared) <= 5:
            return True
    return False


def _scope_shadows(skills: list[SkillRecord], cfg: OptimizerConfig) -> list[Finding]:
    del cfg  # thresholds unused; shadowing is structural by scope
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


def _instruction_conflicts(skills: list[SkillRecord], cfg: OptimizerConfig) -> list[Finding]:
    del cfg
    findings: list[Finding] = []
    for i, a in enumerate(skills):
        for b in skills[i + 1 :]:
            pairs = contradiction_pairs(a.exclusions, b.capabilities + b.triggers)
            pairs += contradiction_pairs(b.exclusions, a.capabilities + a.triggers)
            # Also detect opposing imperative lines sharing subject tokens
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


def _complements(skills: list[SkillRecord], cfg: OptimizerConfig) -> list[Finding]:
    """DEPENDS_ON when one skill references another's name/path as a prerequisite."""
    del cfg
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
    """Find clusters of 3+ skills with pairwise capability overlap."""
    cap_min = float(cfg.thresholds.get("capability_overlap_min", 0.5))
    # Build undirected adjacency
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
