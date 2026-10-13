"""Shared data models for Skill Optimizer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Platform(str, Enum):
    CURSOR = "cursor"
    CLAUDE = "claude"
    CODEX = "codex"
    AGENTS = "agents"
    UNKNOWN = "unknown"


class Scope(str, Enum):
    USER = "user"
    PROJECT = "project"
    BUILTIN = "builtin"
    UNKNOWN = "unknown"


class Origin(str, Enum):
    LOCAL = "local"
    PLUGIN_CACHE = "plugin_cache"
    BUNDLED = "bundled"
    THIRD_PARTY_READONLY = "third_party_readonly"
    SYNTHETIC = "synthetic"


class RelationType(str, Enum):
    DUPLICATE = "DUPLICATE"
    OVERLAPS = "OVERLAPS"
    CONFLICTS = "CONFLICTS"
    COMPLEMENTS = "COMPLEMENTS"
    DEPENDS_ON = "DEPENDS_ON"
    SHADOWS = "SHADOWS"
    POTENTIAL_MERGE = "POTENTIAL_MERGE"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class OperationType(str, Enum):
    REFINE_DESCRIPTION = "REFINE_DESCRIPTION"
    REWRITE_INSTRUCTIONS = "REWRITE_INSTRUCTIONS"
    MERGE_SKILLS = "MERGE_SKILLS"
    SPLIT_SKILL = "SPLIT_SKILL"
    EXTRACT_SHARED_RESOURCE = "EXTRACT_SHARED_RESOURCE"
    CHANGE_SCOPE = "CHANGE_SCOPE"
    FIX_STRUCTURE = "FIX_STRUCTURE"
    DEPRECATE_SKILL = "DEPRECATE_SKILL"
    NO_CHANGE = "NO_CHANGE"


@dataclass(slots=True)
class Frontmatter:
    name: str | None = None
    description: str | None = None
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    allowed_tools: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    parse_error: str | None = None


@dataclass(slots=True)
class SkillResource:
    relative_path: str
    kind: str  # scripts | references | assets | other
    exists: bool
    size_bytes: int = 0
    sha256: str | None = None


@dataclass(slots=True)
class SkillRecord:
    skill_id: str
    path: Path
    skill_md_path: Path
    name: str
    platform: Platform
    scope: Scope
    origin: Origin
    editable: bool
    frontmatter: Frontmatter
    body: str
    description: str
    content_sha256: str
    body_sha256: str
    resources: list[SkillResource] = field(default_factory=list)
    referenced_paths: list[str] = field(default_factory=list)
    broken_links: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    injection_flags: list[str] = field(default_factory=list)
    structural_issues: list[str] = field(default_factory=list)
    related_context_files: list[str] = field(default_factory=list)
    token_estimate: int = 0
    cached: bool = False

    def to_inventory_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "path": str(self.path),
            "skill_md_path": str(self.skill_md_path),
            "name": self.name,
            "platform": self.platform.value,
            "scope": self.scope.value,
            "origin": self.origin.value,
            "editable": self.editable,
            "description": self.description,
            "content_sha256": self.content_sha256,
            "capabilities": self.capabilities,
            "triggers": self.triggers,
            "exclusions": self.exclusions,
            "resources": [asdict(r) for r in self.resources],
            "broken_links": self.broken_links,
            "injection_flags": self.injection_flags,
            "structural_issues": self.structural_issues,
            "related_context_files": self.related_context_files,
            "token_estimate": self.token_estimate,
            "cached": self.cached,
        }


@dataclass(slots=True)
class Evidence:
    kind: str
    detail: str
    files: list[str] = field(default_factory=list)
    metrics: dict[str, float | int | str] = field(default_factory=dict)


@dataclass(slots=True)
class Finding:
    finding_id: str
    relation: RelationType
    severity: Severity
    confidence: float
    skill_ids: list[str]
    title: str
    summary: str
    evidence: list[Evidence] = field(default_factory=list)
    false_positive_risk: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "relation": self.relation.value,
            "severity": self.severity.value,
            "confidence": round(self.confidence, 4),
            "skill_ids": self.skill_ids,
            "title": self.title,
            "summary": self.summary,
            "evidence": [asdict(e) for e in self.evidence],
            "false_positive_risk": self.false_positive_risk,
        }


@dataclass(slots=True)
class GraphEdge:
    source: str
    target: str
    relation: RelationType
    weight: float
    finding_id: str | None = None
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation.value,
            "weight": round(self.weight, 4),
            "finding_id": self.finding_id,
            "evidence": [asdict(e) for e in self.evidence],
        }


@dataclass(slots=True)
class Recommendation:
    recommendation_id: str
    operation: OperationType
    skill_ids: list[str]
    rationale: str
    expected_benefit: str
    risks: list[str]
    verification_criteria: list[str]
    priority: int
    patch_hints: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "operation": self.operation.value,
            "skill_ids": self.skill_ids,
            "rationale": self.rationale,
            "expected_benefit": self.expected_benefit,
            "risks": self.risks,
            "verification_criteria": self.verification_criteria,
            "priority": self.priority,
            "patch_hints": self.patch_hints,
            "requires_confirmation": self.requires_confirmation,
        }


@dataclass(slots=True)
class OptimizationPlan:
    plan_id: str
    created_at: str
    skill_hashes: dict[str, str]
    recommendations: list[Recommendation]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "skill_hashes": self.skill_hashes,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "notes": self.notes,
        }


@dataclass(slots=True)
class ValidationResult:
    name: str
    passed: bool
    measured: bool
    detail: str
    metrics: dict[str, float | int | str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "measured": self.measured,
            "detail": self.detail,
            "metrics": self.metrics,
        }


@dataclass(slots=True)
class MetricsSnapshot:
    routing_accuracy: float | None
    false_activation_rate: float | None
    capability_retention: float | None
    structural_validity: float
    unresolved_conflicts: int
    context_cost_tokens: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "routing_accuracy": self.routing_accuracy,
            "false_activation_rate": self.false_activation_rate,
            "capability_retention": self.capability_retention,
            "structural_validity": self.structural_validity,
            "unresolved_conflicts": self.unresolved_conflicts,
            "context_cost_tokens": self.context_cost_tokens,
            "notes": self.notes,
        }


def severity_rank(severity: Severity) -> int:
    order = {
        Severity.CRITICAL: 5,
        Severity.HIGH: 4,
        Severity.MEDIUM: 3,
        Severity.LOW: 2,
        Severity.INFO: 1,
    }
    return order[severity]
