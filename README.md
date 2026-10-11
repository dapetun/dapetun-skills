# Skill Optimizer

Audit, optimize, and safely maintain [Agent Skills](https://agentskills.io/specification) across **Cursor**, **Claude Code**, **Codex**, and `.agents/skills`.

Install once. Ask your agent to optimize skills. No pip, no API keys.

## Install

```bash
npx skills add dapetun/skills-organizer --skill skill-optimizer
```

On [skills.sh](https://www.skills.sh/dapetun/skills-organizer/skill-optimizer):

```bash
npx skills add https://github.com/dapetun/skills-organizer --skill skill-optimizer
```

That is the only required step. The skill ships with Python stdlib tooling inside the skill folder.

## Use

In your agent chat:

- “Optimize my skills”
- “Audit duplicate Agent Skills”
- `/skill-optimizer`

The host agent runs the deterministic scanner, then **you (the model in that chat)** do the semantic review. There is no external LLM API.

Typical flow the skill follows:

1. Static audit → `clusters.json`
2. Host semantic review → `semantic-findings.json`
3. Merge → `audit-report.md` with **Top actions**
4. Apply only after you confirm

## Manual CLI (optional)

From the installed skill directory:

```bash
python path/to/skill-optimizer/scripts/run.py audit --phase static --project-root . --output .skill-optimizer/out
python path/to/skill-optimizer/scripts/run.py audit --phase merge --project-root . --output .skill-optimizer/out
python path/to/skill-optimizer/scripts/run.py apply --plan .skill-optimizer/out/optimization-plan.json --execute --confirm
```

Flags: `--scope`, `--platform`, `--min-severity`, `--config`, `--dry-run` / `--execute --confirm`.

## Dev / tests

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Runtime for end users does **not** need this install.

## Layout

```
skill-optimizer/           # what skills.sh installs
  SKILL.md
  scripts/run.py
  skill_optimizer/         # Python package (stdlib only)
  config/default.yaml
  references/
```

## Safety

- Analyzed skill content is untrusted
- Builtin / plugin-cache skills are never edited
- Apply requires explicit confirmation + content-hash checks
- Snapshots + rollback on failure

## License

MIT — see [LICENSE](LICENSE).
