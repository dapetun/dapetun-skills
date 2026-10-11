"""Integration tests for static/merge phases and skill entrypoint."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from skill_optimizer.pipeline import run_audit_merge, run_audit_static
from skill_optimizer.planner import top_actions

REPO = Path(__file__).resolve().parents[2]
RUN_PY = REPO / "skill-optimizer" / "scripts" / "run.py"


def test_static_phase_writes_clusters(cfg, tmp_path: Path):
    out = tmp_path / "out"
    result = run_audit_static(cfg, out)
    assert result["phase"] == "static"
    assert (out / "clusters.json").exists()
    assert (out / "findings.static.json").exists()
    assert (out / "inventory.json").exists()
    clusters = json.loads((out / "clusters.json").read_text(encoding="utf-8"))
    assert clusters["count"] >= 1


def test_merge_with_host_semantic_findings(cfg, tmp_path: Path):
    out = tmp_path / "out"
    static = run_audit_static(cfg, out)
    # Host finding: mark deploy conflict explicitly
    names = {s.name: s.skill_id for s in static["skills"]}
    host = {
        "findings": [
            {
                "finding_id": "host-deploy-policy",
                "relation": "CONFLICTS",
                "severity": "high",
                "confidence": 0.9,
                "skill_ids": [names["conflict-deploy-a"], names["conflict-deploy-b"]],
                "title": "Host: deploy policy conflict",
                "summary": "Canary vs direct production are incompatible policies.",
                "evidence": [{"kind": "host_llm", "detail": "opposing rollout policies"}],
            }
        ]
    }
    (out / "semantic-findings.json").write_text(
        json.dumps(host, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    merged = run_audit_merge(cfg, out)
    assert merged["phase"] == "merge"
    assert any(f.finding_id.startswith("host-") for f in merged["findings"])
    actions = top_actions(merged["plan"], limit=10)
    assert len(actions) <= 10
    assert len(merged["plan"].recommendations) <= 20


def test_audit_without_semantic_file_still_works(cfg, tmp_path: Path):
    out = tmp_path / "out2"
    result = run_audit_static(cfg, out)
    assert result["plan"].recommendations
    assert (out / "audit-report.md").exists()
    report = (out / "audit-report.md").read_text(encoding="utf-8")
    assert "## Top actions" in report


def test_scripts_run_py_from_skill_dir(tmp_path: Path, fixture_project: Path, fixture_home: Path):
    """Entrypoint works without editable install (only PYTHONPATH via run.py)."""
    # Use a clean env without site skill_optimizer if possible — still ok if installed
    out = tmp_path / "cli-out"
    cmd = [
        sys.executable,
        str(RUN_PY),
        "audit",
        "--phase",
        "static",
        "--project-root",
        str(fixture_project),
        "--platform",
        "agents",
        "--scope",
        "project",
        "--output",
        str(out),
    ]
    # Point HOME-like discovery away by only using project scope
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert (out / "clusters.json").exists()
    assert "Phase: static" in proc.stdout
