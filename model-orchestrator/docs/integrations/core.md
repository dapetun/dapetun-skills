# Core profile — standalone orchestrator

**Last updated:** 2026-10-03

Works **without** Hindsight or GitNexus. Recommend-only skill + YAML routing.

## Install

From the skills directory (core bundle: routes, catalog, budget policy, `sync_budget.py`):

```powershell
npx skills add dapetun/dapetun-skills --skill model-orchestrator -a cursor -g
```

Full clone when you want local `projects.yaml` path prefixes. `install_skill.ps1` writes `ORCHESTRATOR_ROOT.txt`, which overrides the bundled snapshot:

```powershell
git clone https://github.com/dapetun/dapetun-skills.git
cd dapetun-skills/model-orchestrator
Copy-Item config\projects.example.yaml config\projects.yaml   # if missing
# Edit config/projects.yaml with your local path_prefixes
pwsh -File .\scripts\install_skill.ps1 -Profile core
```

Restart Cursor or open a new Agent chat.

## What you get

- Russian `[route]` with `tier`, `model`, `mode`, `pool`, `budget`, `shape`
- Budget / eco / exhausted Cursor-only matrix
- Fable HITL
- **No** Hindsight retain (skipped silently)
- **No** GitNexus requirements

## Config

| File | Role |
| --- | --- |
| `config/integrations.yaml` | `profile: core` after install |
| `config/routes.yaml` | tiers, plan_shapes, exhausted matrix |
| `config/projects.yaml` | local (gitignored); start from `projects.example.yaml` |
| `config/budget.yaml` | Thresholds (`warn_at_ratio`, monthly heuristic) |
| `config/budget.local.yaml` | Live Other Models % from `scripts/sync_budget.py` (gitignored) |

## Verify

See [acceptance-v0.md](../acceptance-v0.md) scenarios 1–15 and **16** (core skip retain).
