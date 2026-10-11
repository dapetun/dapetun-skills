"""Unit tests for analyzers using synthetic library."""

from __future__ import annotations

from skill_optimizer.models import RelationType


def _by_name(skills):
    return {s.name: s for s in skills}


def test_discovers_skills_and_related_context(skills, fixture_project):
    names = {s.name for s in skills}
    assert "healthy-unique" in names
    assert "shared-dup" in names
    assert "scope-twin" in names
    # AGENTS.md is related context, not a skill
    assert all(s.skill_md_path.name == "SKILL.md" for s in skills)
    related = skills[0].related_context_files
    assert any(str(fixture_project / "AGENTS.md") == r or r.endswith("AGENTS.md") for r in related)


def test_exact_duplicates(analyzed):
    skills, findings, _graph, _plan = analyzed
    dups = [f for f in findings if f.relation == RelationType.DUPLICATE]
    assert dups, "expected exact duplicate finding"
    involved = set()
    for f in dups:
        involved.update(f.skill_ids)
    names = {s.name for s in skills if s.skill_id in involved}
    assert "shared-dup" in names
    assert len([s for s in skills if s.name == "shared-dup"]) >= 2


def test_similar_but_specialized_not_forced_merge(analyzed):
    skills, findings, _graph, plan = analyzed
    by = _by_name(skills)
    a = by["similar-pdf-extract"]
    b = by["similar-pdf-forms"]
    pair_findings = [
        f
        for f in findings
        if set(f.skill_ids) == {a.skill_id, b.skill_id}
    ]
    # Should recognize complementarity / specialization, not only merge
    assert any(f.relation == RelationType.COMPLEMENTS for f in pair_findings) or any(
        r.operation.value == "NO_CHANGE" and set(r.skill_ids) >= {a.skill_id, b.skill_id}
        for r in plan.recommendations
    ) or any(f.relation == RelationType.COMPLEMENTS for f in findings)
    # Must NOT have a high-confidence forced merge solely due to PDF wording
    forced = [
        r
        for r in plan.recommendations
        if r.operation.value == "MERGE_SKILLS"
        and set(r.skill_ids) == {a.skill_id, b.skill_id}
    ]
    assert not forced, "similar specialized PDF skills must not be auto-merged"


def test_contradictory_deploy_skills(analyzed):
    skills, findings, _graph, _plan = analyzed
    by = _by_name(skills)
    a = by["conflict-deploy-a"]
    b = by["conflict-deploy-b"]
    conflicts = [
        f
        for f in findings
        if f.relation == RelationType.CONFLICTS
        and {a.skill_id, b.skill_id} <= set(f.skill_ids)
    ]
    assert conflicts


def test_scope_shadow(analyzed):
    _skills, findings, _graph, _plan = analyzed
    shadows = [f for f in findings if f.relation == RelationType.SHADOWS and "scope-twin" in f.title]
    assert shadows


def test_broad_description(analyzed):
    skills, findings, _graph, plan = analyzed
    broad = _by_name(skills)["broad-helper"]
    assert any(broad.skill_id in f.skill_ids and "broad" in f.finding_id for f in findings) or any(
        r.operation.value == "REFINE_DESCRIPTION" and broad.skill_id in r.skill_ids
        for r in plan.recommendations
    )


def test_broken_yaml_and_links(analyzed):
    skills, findings, _graph, plan = analyzed
    by = _by_name(skills)
    yaml_skill = by["broken-yaml-skill"]
    links_skill = by["broken-links-skill"]
    assert yaml_skill.structural_issues
    assert links_skill.broken_links
    assert any("FIX_STRUCTURE" == r.operation.value for r in plan.recommendations)


def test_cluster_of_three(analyzed):
    skills, findings, _graph, _plan = analyzed
    by = _by_name(skills)
    ids = {by[n].skill_id for n in ("cluster-one", "cluster-two", "cluster-three")}
    cluster = [
        f
        for f in findings
        if f.relation == RelationType.OVERLAPS and ids <= set(f.skill_ids)
    ]
    assert cluster, "expected 3+ skill overlap cluster"


def test_injection_detected(analyzed):
    skills, findings, _graph, plan = analyzed
    trap = _by_name(skills)["injection-trap"]
    assert trap.injection_flags
    assert any(
        trap.skill_id in f.skill_ids and f.severity.value == "critical" for f in findings
    ) or any(
        trap.skill_id in r.skill_ids and r.operation.value == "REWRITE_INSTRUCTIONS"
        for r in plan.recommendations
    )


def test_healthy_unique_no_false_positive_problem(analyzed):
    skills, findings, _graph, plan = analyzed
    healthy = _by_name(skills)["healthy-unique"]
    # Findings that primarily target this skill alone must not be problem-class
    solo_problems = [
        f
        for f in findings
        if f.skill_ids == [healthy.skill_id]
        and f.relation
        in {
            RelationType.DUPLICATE,
            RelationType.CONFLICTS,
            RelationType.POTENTIAL_MERGE,
            RelationType.SHADOWS,
            RelationType.OVERLAPS,
        }
    ]
    assert not solo_problems
    assert not healthy.structural_issues
    mutate = [
        r
        for r in plan.recommendations
        if r.skill_ids == [healthy.skill_id]
        and r.operation.value
        in {"MERGE_SKILLS", "DEPRECATE_SKILL", "REWRITE_INSTRUCTIONS", "FIX_STRUCTURE"}
    ]
    assert not mutate
