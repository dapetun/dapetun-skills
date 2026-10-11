# Skill Optimizer

Audit, optimize, and safely maintain [Agent Skills](https://agentskills.io/specification) ecosystems across **Cursor**, **Claude Code**, **Codex**, and universal `.agents/skills` paths.

**Priority:** diagnostic quality → minimal necessary changes → verification. The goal is ecosystem coherence and routing effectiveness, not minimizing skill count or tokens at any cost.

## Features

- **Discovery** of user/project/builtin skills with platform adapters
- **Static analysis** (YAML frontmatter, structure, exact duplicates, broken links)
- **Semantic heuristics** (capabilities, triggers, conflicts, clusters, specialization vs duplication)
- **Conflict graph** with `DUPLICATE`, `OVERLAPS`, `CONFLICTS`, `COMPLEMENTS`, `DEPENDS_ON`, `SHADOWS`, `POTENTIAL_MERGE`
- **Optimization planner** with verifiable recommendations
- **Safe apply** (read-only default, diffs, snapshots, staging, rollback)
- **Validation** with simulated routing metrics (no fabricated “measured” values)
- **Baseline mode without LLM/embeddings** (optional LLM hook, disabled by default)
- Treats skill content as **untrusted** (injection detection, path traversal guards, never executes skill scripts)

## Install

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -e ".[dev]"
```

Requires Python 3.10+.

## CLI

```bash
# Diagnose (no writes)
skill-optimizer audit --project-root . --output reports/audit

# Build plan artifacts
skill-optimizer plan --project-root . --output reports/plan

# Check one skill
skill-optimizer check ./path/to/skill --output reports/check

# Preview apply
skill-optimizer apply --plan reports/plan/optimization-plan.json

# Apply after explicit approval
skill-optimizer apply --plan reports/plan/optimization-plan.json --execute --confirm

# Rollback a snapshot
skill-optimizer rollback <snapshot_id>
```

Filters:

```bash
skill-optimizer audit --scope user --scope project --platform cursor --output reports/cursor
skill-optimizer audit --extra-root ./my-skills --config ./config/default.yaml
```

## Reports

| File | Description |
| --- | --- |
| `inventory.json` | Catalog of discovered skills |
| `findings.json` | Issues with evidence, severity, confidence |
| `skill-graph.json` | Relationship graph |
| `optimization-plan.json` | Recommendations + verification criteria |
| `audit-report.md` | Human-readable summary |
| `validation-report.json` | Checks + metrics |
| `execution-manifest.json` | Apply history / last apply result |

Metrics include routing accuracy, false activation rate, capability retention, structural validity, unresolved conflicts, and context cost. Values are reported as **measured** only when corresponding tests ran; otherwise they are `n/a` with notes.

## Agent skill

This repo includes a meta-skill at [`skill-optimizer/SKILL.md`](skill-optimizer/SKILL.md). Copy or symlink it into your skills directory, or point agents at this repository.

## Configuration

See [`config/default.yaml`](config/default.yaml) for platforms, discovery roots, thresholds, weights, security patterns, cache, and apply policy.

## Tests

```bash
pytest
# or
pytest --cov=skill_optimizer
```

Synthetic fixture library under `tests/fixtures/skill_library` covers duplicates, specialization, conflicts, scope shadows, broad descriptions, broken YAML/links, merges, clusters, stale plans, rollback, injection, and the healthy no-change case.

## Architecture

```
src/skill_optimizer/
  discovery.py          # locate skills
  parser.py             # SKILL.md + agentskills.io validation
  static_analyzer.py    # structure / duplicates
  semantic_analyzer.py  # capabilities / conflicts (LLM optional)
  conflict_graph.py     # relation graph
  planner.py            # recommendations
  validation.py         # simulation + retention checks
  apply_engine.py       # snapshots / staging / rollback
  reporting.py          # artifacts
  cli.py                # audit|plan|apply|check|rollback
```

Python owns deterministic analysis and safe mutation. LLM assistance is optional and never required.

## Safety notes

- Builtin / plugin-cache skills are discovered as non-editable
- Apply refuses writes without `--execute --confirm`
- Plans embed content hashes; changed skills invalidate apply
- Analyzed skill bodies are never executed

## License

MIT — see [LICENSE](LICENSE).
