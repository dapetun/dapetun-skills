# Stack profile — orchestrator + Hindsight ondemand (+ optional GitNexus)

**Last updated:** 2026-10-03

**Router** = this repo. **Hindsight lifecycle** = [cursor-hindsight-ondemand](https://github.com/dapetun/cursor-hindsight-ondemand). **GitNexus** = upstream MCP/CLI (not vendored here).

## Install order

1. **This repo (stack profile)**

```powershell
cd dapetun-skills/model-orchestrator
Copy-Item config\projects.example.yaml config\projects.yaml   # if missing; edit paths
pwsh -File .\scripts\install_skill.ps1 -Profile stack
```

Sets `config/integrations.yaml` and skill-local copy to `hindsight.enabled: true`, `gitnexus.enabled: true`.

2. **Hindsight ondemand** (required for retain)

```powershell
git clone https://github.com/dapetun/cursor-hindsight-ondemand.git
cd cursor-hindsight-ondemand
.\install.ps1
.\install.ps1 -WriteHooks -WriteMcp -WriteCursorJson   # optional helpers
```

Keep `"hindsightApiUrl": "http://127.0.0.1:9077"` in `~/.hindsight/cursor.json`.

**MCP server name** expected by the orchestrator skill: `hindsight` (see `integrations.yaml` → `hindsight.mcp_server`). Align ondemand `examples/mcp.json` with that name.

3. **GitNexus (optional)**

- Install GitNexus MCP for Cursor ([upstream](https://github.com/abhigyanpatwari/GitNexus)).
- In coding repos: `npx gitnexus analyze` (or project runner) so impact / detect_changes work.
- Orchestrator only **hints**; it never hard-requires GitNexus.

## Soft behavior

| Tool | If missing |
| --- | --- |
| Hindsight MCP | Skip retain; `[route]` still printed |
| GitNexus | Skip impact hint; routing unchanged |

**Privacy:** retain must be lean route metadata only — never full prompts, code, secrets, or PII ([hindsight-schema.md](../hindsight-schema.md), [legal/privacy.md](../legal/privacy.md)).

## Division of responsibility

| Concern | Repo |
| --- | --- |
| Model tier / budget / `[route]` | dapetun-skills / model-orchestrator |
| Start local Hindsight daemon on demand | cursor-hindsight-ondemand |
| Code graph impact analysis | GitNexus upstream |

## Verify

Acceptance scenarios **16** (core) vs **17** (stack + retain when MCP up) in [acceptance-v0.md](../acceptance-v0.md).
