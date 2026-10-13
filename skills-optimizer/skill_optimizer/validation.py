"""Validation and regression checks (simulation vs optional runtime)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from skill_optimizer.config import OptimizerConfig
from skill_optimizer.models import (
    Finding,
    MetricsSnapshot,
    OptimizationPlan,
    RelationType,
    SkillRecord,
    ValidationResult,
)
from skill_optimizer.textutil import jaccard, token_set

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RoutingProbe:
    prompt: str
    expected_skill_names: set[str]
    forbidden_skill_names: set[str]


def default_probes(skills: list[SkillRecord]) -> list[RoutingProbe]:
    """Build deterministic probes from skill descriptions/triggers."""
    probes: list[RoutingProbe] = []
    for skill in skills:
        # Positive probe: use distinctive tokens from name + first triggers
        cues = [skill.name.replace("-", " ")]
        cues.extend(skill.triggers[:3])
        prompt = "Please help with " + "; ".join(cues)
        probes.append(
            RoutingProbe(
                prompt=prompt,
                expected_skill_names={skill.name},
                forbidden_skill_names=set(),
            )
        )
    # Negative / false-activation probes for broad skills
    for skill in skills:
        if len(skill.triggers) >= 12 or len(skill.description) >= 900:
            probes.append(
                RoutingProbe(
                    prompt="What is the weather in Paris today?",
                    expected_skill_names=set(),
                    forbidden_skill_names={skill.name},
                )
            )
    return probes


def simulate_route(prompt: str, skills: list[SkillRecord]) -> list[tuple[str, float]]:
    """Score skills for a prompt without calling an LLM (deterministic)."""
    prompt_tokens = token_set(prompt)
    scored: list[tuple[str, float]] = []
    for skill in skills:
        desc_score = jaccard(prompt_tokens, token_set(skill.description))
        trig_score = jaccard(prompt_tokens, token_set(" ".join(skill.triggers)))
        name_bonus = 0.25 if skill.name.replace("-", " ") in prompt.lower() else 0.0
        # Exact name token presence
        if skill.name in prompt or skill.name.replace("-", " ") in prompt.lower():
            name_bonus = 0.35
        score = 0.45 * desc_score + 0.45 * trig_score + name_bonus
        scored.append((skill.name, score))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored


def select_skills(prompt: str, skills: list[SkillRecord], threshold: float = 0.2) -> list[str]:
    scored = simulate_route(prompt, skills)
    selected = [name for name, score in scored if score >= threshold]
    return selected[:3]


def validate_inventory(skills: list[SkillRecord]) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    valid = sum(1 for s in skills if not s.structural_issues)
    total = len(skills) or 1
    results.append(
        ValidationResult(
            name="structural_validity",
            passed=valid == len(skills),
            measured=True,
            detail=f"{valid}/{len(skills)} skills pass structural checks",
            metrics={"valid": valid, "total": len(skills), "ratio": valid / total},
        )
    )
    inj = [s.name for s in skills if s.injection_flags]
    results.append(
        ValidationResult(
            name="injection_clean",
            passed=not inj,
            measured=True,
            detail="No injection markers" if not inj else f"Flagged: {', '.join(inj)}",
            metrics={"flagged": len(inj)},
        )
    )
    return results


def validate_routing(
    skills: list[SkillRecord],
    probes: Iterable[RoutingProbe] | None = None,
) -> list[ValidationResult]:
    probes = list(probes or default_probes(skills))
    if not probes:
        return [
            ValidationResult(
                name="routing_accuracy",
                passed=True,
                measured=False,
                detail="No probes available; metric not measured",
            )
        ]
    hits = 0
    false_acts = 0
    false_denom = 0
    for probe in probes:
        selected = set(select_skills(probe.prompt, skills))
        if probe.expected_skill_names:
            if probe.expected_skill_names & selected:
                hits += 1
        else:
            # Pure negative probe
            pass
        if probe.forbidden_skill_names:
            false_denom += 1
            if probe.forbidden_skill_names & selected:
                false_acts += 1
    expected_probes = [p for p in probes if p.expected_skill_names]
    accuracy = hits / len(expected_probes) if expected_probes else None
    far = false_acts / false_denom if false_denom else None
    results = [
        ValidationResult(
            name="routing_accuracy",
            passed=accuracy is None or accuracy >= 0.5,
            measured=accuracy is not None,
            detail=(
                f"Measured routing accuracy={accuracy:.3f} on {len(expected_probes)} probes"
                if accuracy is not None
                else "Not measured"
            ),
            metrics={
                "hits": hits,
                "expected_probes": len(expected_probes),
                "accuracy": accuracy if accuracy is not None else "null",
            },
        ),
        ValidationResult(
            name="false_activation_rate",
            passed=far is None or far <= 0.5,
            measured=far is not None,
            detail=(
                f"Measured false activation rate={far:.3f} on {false_denom} negative probes"
                if far is not None
                else "Not measured (no negative probes)"
            ),
            metrics={
                "false_activations": false_acts,
                "negative_probes": false_denom,
                "rate": far if far is not None else "null",
            },
        ),
    ]
    return results


def capability_retention(
    before: list[SkillRecord],
    after: list[SkillRecord],
) -> ValidationResult:
    before_caps = set()
    for s in before:
        before_caps.update(s.capabilities)
    after_caps = set()
    for s in after:
        after_caps.update(s.capabilities)
    if not before_caps:
        return ValidationResult(
            name="capability_retention",
            passed=True,
            measured=True,
            detail="No capabilities extracted before; retention trivially satisfied",
            metrics={"retention": 1.0},
        )
    retained = before_caps & after_caps
    ratio = len(retained) / len(before_caps)
    return ValidationResult(
        name="capability_retention",
        passed=ratio >= 1.0,
        measured=True,
        detail=f"Capability retention={ratio:.3f} ({len(retained)}/{len(before_caps)})",
        metrics={
            "before": len(before_caps),
            "after": len(after_caps),
            "retained": len(retained),
            "retention": ratio,
        },
    )


def validate_plan_hashes(
    plan: OptimizationPlan,
    skills: list[SkillRecord],
) -> ValidationResult:
    current = {s.skill_id: s.content_sha256 for s in skills}
    mismatches = []
    for skill_id, digest in plan.skill_hashes.items():
        if skill_id not in current:
            mismatches.append(f"missing:{skill_id}")
        elif current[skill_id] != digest:
            mismatches.append(f"changed:{skill_id}")
    return ValidationResult(
        name="plan_hash_freshness",
        passed=not mismatches,
        measured=True,
        detail="Plan hashes match current skills"
        if not mismatches
        else f"Stale plan; changed skills: {', '.join(mismatches)}",
        metrics={"mismatches": len(mismatches)},
    )


def compute_metrics(
    skills: list[SkillRecord],
    findings: list[Finding],
    validation_results: list[ValidationResult],
) -> MetricsSnapshot:
    by_name = {r.name: r for r in validation_results}
    routing = by_name.get("routing_accuracy")
    far = by_name.get("false_activation_rate")
    retention = by_name.get("capability_retention")
    structural = by_name.get("structural_validity")
    # Считать только жёсткие нерешённые проблемы, не весь pairwise-шум OVERLAPS
    unresolved = sum(
        1
        for f in findings
        if f.relation
        in {
            RelationType.DUPLICATE,
            RelationType.CONFLICTS,
            RelationType.SHADOWS,
        }
        and f.severity.value in {"critical", "high"}
        and f.confidence >= 0.7
    )
    notes = []
    for r in validation_results:
        if not r.measured:
            notes.append(f"{r.name}: not measured — {r.detail}")
    return MetricsSnapshot(
        routing_accuracy=(
            float(routing.metrics["accuracy"])
            if routing and routing.measured and isinstance(routing.metrics.get("accuracy"), float)
            else None
        ),
        false_activation_rate=(
            float(far.metrics["rate"])
            if far and far.measured and isinstance(far.metrics.get("rate"), float)
            else None
        ),
        capability_retention=(
            float(retention.metrics["retention"])
            if retention and retention.measured
            else None
        ),
        structural_validity=float(structural.metrics.get("ratio", 0.0)) if structural else 0.0,
        unresolved_conflicts=unresolved,
        context_cost_tokens=sum(s.token_estimate for s in skills),
        notes=notes,
    )


def run_validation(
    skills: list[SkillRecord],
    findings: list[Finding],
    cfg: OptimizerConfig,
    *,
    before_skills: list[SkillRecord] | None = None,
    plan: OptimizationPlan | None = None,
) -> tuple[list[ValidationResult], MetricsSnapshot]:
    results: list[ValidationResult] = []
    results.extend(validate_inventory(skills))
    if cfg.validation.get("simulate_routing", True):
        results.extend(validate_routing(skills))
    if before_skills is not None:
        results.append(capability_retention(before_skills, skills))
    if plan is not None:
        results.append(validate_plan_hashes(plan, skills))
    if not cfg.validation.get("runtime_tests", False):
        results.append(
            ValidationResult(
                name="runtime_tests",
                passed=True,
                measured=False,
                detail="Runtime agent tests disabled (simulation only)",
            )
        )
    metrics = compute_metrics(skills, findings, results)
    logger.info("Validation completed with %d results", len(results))
    return results, metrics


_FRONTMATTER_NAME = re.compile(r"(?m)^name:\s*(.+)$")
