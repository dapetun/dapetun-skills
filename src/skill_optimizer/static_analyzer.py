"""Static analysis: structure, exact duplicates, repeated instructions."""

from __future__ import annotations

import logging
from collections import defaultdict

from skill_optimizer.config import OptimizerConfig
from skill_optimizer.models import (
    Evidence,
    Finding,
    RelationType,
    Severity,
    SkillRecord,
)
from skill_optimizer.textutil import jaccard, repeated_instruction_lines, token_set

logger = logging.getLogger(__name__)


def analyze_static(skills: list[SkillRecord], cfg: OptimizerConfig) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_structural_findings(skills))
    findings.extend(_exact_duplicates(skills, cfg))
    findings.extend(_near_duplicate_bodies(skills, cfg))
    findings.extend(_repeated_instructions(skills, cfg))
    findings.extend(_broad_descriptions(skills, cfg))
    logger.info("Static analyzer produced %d findings", len(findings))
    return findings


def _structural_findings(skills: list[SkillRecord]) -> list[Finding]:
    out: list[Finding] = []
    for skill in skills:
        if not skill.structural_issues:
            continue
        severity = Severity.HIGH
        if any("prompt-injection" in i.lower() for i in skill.structural_issues):
            severity = Severity.CRITICAL
        elif any("Missing required" in i or "Invalid YAML" in i for i in skill.structural_issues):
            severity = Severity.HIGH
        elif skill.broken_links:
            severity = Severity.MEDIUM
        out.append(
            Finding(
                finding_id=f"struct-{skill.content_sha256[:10]}",
                relation=RelationType.CONFLICTS,
                severity=severity,
                confidence=0.95,
                skill_ids=[skill.skill_id],
                title=f"Structural issues in {skill.name}",
                summary="; ".join(skill.structural_issues),
                evidence=[
                    Evidence(
                        kind="structure",
                        detail=issue,
                        files=[str(skill.skill_md_path)],
                    )
                    for issue in skill.structural_issues
                ],
            )
        )
    return out


def _exact_duplicates(skills: list[SkillRecord], cfg: OptimizerConfig) -> list[Finding]:
    if not cfg.thresholds.get("exact_duplicate_hash", True):
        return []
    by_hash: dict[str, list[SkillRecord]] = defaultdict(list)
    for skill in skills:
        by_hash[skill.content_sha256].append(skill)
    findings: list[Finding] = []
    for digest, group in by_hash.items():
        if len(group) < 2:
            continue
        ids = [s.skill_id for s in group]
        findings.append(
            Finding(
                finding_id=f"dup-{digest[:12]}",
                relation=RelationType.DUPLICATE,
                severity=Severity.HIGH,
                confidence=1.0,
                skill_ids=ids,
                title="Exact duplicate SKILL.md content",
                summary=(
                    f"{len(group)} skills share identical content hash {digest[:12]}: "
                    + ", ".join(s.name for s in group)
                ),
                evidence=[
                    Evidence(
                        kind="content_hash",
                        detail=digest,
                        files=[str(s.skill_md_path) for s in group],
                        metrics={"count": len(group)},
                    )
                ],
            )
        )
    return findings


def _near_duplicate_bodies(skills: list[SkillRecord], cfg: OptimizerConfig) -> list[Finding]:
    threshold = float(cfg.thresholds.get("body_jaccard_overlap", 0.85))
    findings: list[Finding] = []
    for i, a in enumerate(skills):
        a_tokens = token_set(a.body)
        for b in skills[i + 1 :]:
            if a.content_sha256 == b.content_sha256:
                continue
            score = jaccard(a_tokens, token_set(b.body))
            if score < threshold:
                continue
            # High textual overlap alone is POTENTIAL_MERGE / OVERLAPS, not auto-merge.
            findings.append(
                Finding(
                    finding_id=f"near-{a.content_sha256[:6]}-{b.content_sha256[:6]}",
                    relation=RelationType.POTENTIAL_MERGE,
                    severity=Severity.MEDIUM,
                    confidence=min(0.9, score),
                    skill_ids=[a.skill_id, b.skill_id],
                    title="High body text overlap",
                    summary=(
                        f"{a.name} and {b.name} share Jaccard={score:.2f} body tokens. "
                        "Text similarity alone is insufficient for merge; check capabilities."
                    ),
                    evidence=[
                        Evidence(
                            kind="jaccard_body",
                            detail="Body token Jaccard overlap",
                            files=[str(a.skill_md_path), str(b.skill_md_path)],
                            metrics={"jaccard": round(score, 4)},
                        )
                    ],
                    false_positive_risk="medium",
                )
            )
    return findings


def _repeated_instructions(skills: list[SkillRecord], cfg: OptimizerConfig) -> list[Finding]:
    min_count = int(cfg.thresholds.get("instruction_line_repeat_min", 3))
    findings: list[Finding] = []
    for skill in skills:
        repeats = repeated_instruction_lines(skill.body, min_count=min_count)
        if not repeats:
            continue
        findings.append(
            Finding(
                finding_id=f"repeat-{skill.content_sha256[:10]}",
                relation=RelationType.OVERLAPS,
                severity=Severity.LOW,
                confidence=0.8,
                skill_ids=[skill.skill_id],
                title=f"Repeated instruction lines in {skill.name}",
                summary=f"Found {len(repeats)} heavily repeated instruction lines",
                evidence=[
                    Evidence(
                        kind="repeated_line",
                        detail=line,
                        files=[str(skill.skill_md_path)],
                        metrics={"count": count},
                    )
                    for line, count in repeats[:5]
                ],
            )
        )
    return findings


def _broad_descriptions(skills: list[SkillRecord], cfg: OptimizerConfig) -> list[Finding]:
    max_chars = int(cfg.thresholds.get("broad_description_max_chars", 900))
    min_triggers = int(cfg.thresholds.get("broad_description_min_triggers", 12))
    findings: list[Finding] = []
    for skill in skills:
        desc = skill.description or ""
        # Require a long description; trigger count alone is not enough
        # (avoids false positives on focused skills with detailed "use when" clauses).
        if len(desc) < max_chars:
            continue
        trigger_phrases = [t for t in skill.triggers if " " in t or len(t) > 24]
        if len(desc) >= max_chars or len(trigger_phrases) >= min_triggers:
            findings.append(
                Finding(
                    finding_id=f"broad-{skill.content_sha256[:10]}",
                    relation=RelationType.SHADOWS,
                    severity=Severity.MEDIUM,
                    confidence=0.7,
                    skill_ids=[skill.skill_id],
                    title=f"Overly broad description: {skill.name}",
                    summary=(
                        f"Description length={len(desc)}, extracted trigger phrases="
                        f"{len(trigger_phrases)}. May cause false activations."
                    ),
                    evidence=[
                        Evidence(
                            kind="broad_description",
                            detail=desc[:300],
                            files=[str(skill.skill_md_path)],
                            metrics={
                                "description_chars": len(desc),
                                "trigger_phrase_count": len(trigger_phrases),
                            },
                        )
                    ],
                    false_positive_risk="medium",
                )
            )
    return findings
