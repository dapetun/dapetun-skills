# Reference routes (cheat sheet)

Use when YAML configs are unavailable. Prefer `config/routes.yaml` when present.

## Doctrine (v1 — Cursor models only)

**Grok 4.7 standard plans / analyzes. Composer 2.5 standard executes code and file ops.**
Third-party models are never in the matrix. Fast / 500k only if the user asked.

| роль | Typical model (balance, pool OK) |
| --- | --- |
| план | Grok 4.7 standard (не Fast) |
| код | Composer 2.5 standard (не Fast) |
| анализ | Grok 4.7 standard (не Fast) |

Routine tiers may show **Auto Cost** when the plan offers Auto (Plus → Composer).

## [route] machine fields (v1)

```text
[route] project=… tier=… model=… mode=… pool=… budget=… shape=… роль=<план|код|анализ>
```

| Field | Values |
| --- | --- |
| pool | `cursor` \| `paid` |
| budget | `ok` \| `warn` \| `exhausted` \| `unknown` |
| shape | `none` \| `mapper` \| `specialist` \| `pipeline` \| `hybrid` |
| роль | `план` \| `код` \| `анализ` |

### plan_shapes fallback (if YAML missing)

| Tier | shape |
| --- | --- |
| parallel_roles | specialist |
| refactor_architecture | pipeline |
| long_agent | hybrid |
| all others | none |

Splitter hint only — **never spawn**.

## Profiles (integrations.yaml)

| Profile | Hindsight retain | GitNexus hint |
| --- | --- | --- |
| `core` (default) | skip | skip |
| `stack` | if MCP `hindsight` available | if GitNexus available, coding tiers only |

Stack Hindsight install: https://github.com/dapetun/cursor-hindsight-ondemand

**Privacy:** retain lean route fields only — never prompts/PII.

## Modes

- `eco` → Composer 2.5 standard only
- `balance` → Auto Cost / Composer routine; Grok plan/analyze on hard tiers; Composer code
- `max` → Grok 4.7 standard for hard plan **and** heavy execute; still no Fast / no third-party

## Tier → model (balance / pool OK)

| Tier | роль=план / анализ | роль=код |
| --- | --- | --- |
| quick_edit | — | Auto Cost / Composer 2.5 standard |
| default_code | — | Auto Cost → Composer 2.5 standard |
| research_docs | Auto Cost (max → Grok) | Composer 2.5 standard |
| cursor_meta | — | Composer 2.5 standard |
| docs_office | Auto Cost (academic → paper) | Composer 2.5 standard |
| frontend_design | Grok 4.7 standard | Composer 2.5 standard |
| paper | Grok 4.7 standard | Composer if tooling code |
| science_stats | Grok 4.7 standard (Q&A) | Composer 2.5 standard (implement) |
| refactor_architecture | Grok 4.7 standard | Composer 2.5 standard |
| long_agent | Grok 4.7 standard | Composer 2.5 standard |
| parallel_roles | advise role map | coder = Composer |

## max mode upgrades

- Hard plan/execute → Grok 4.7 standard (не Fast, не xhigh as a price lever)
- Still no third-party models

## eco / exhausted / hard-block (Composer-only matrix)

Triggers: `/eco`, pool exhausted, hard-block@warn_ratio without HITL paid override.

| Tier | Model |
| --- | --- |
| all listed tiers | Composer 2.5 standard |
| science_stats | Composer + **mandatory** science warning |
| parallel_roles | role_map_exhausted (all Composer) |

### role_map (pool OK)

| Role | Model |
| --- | --- |
| planner | Grok 4.7 standard |
| coder | Composer 2.5 standard |
| reviewer | Grok 4.7 standard |
| researcher | Grok 4.7 standard |
| verifier | Composer 2.5 standard |
| scientist | Grok 4.7 standard |

### role_map_exhausted

| Role | Model |
| --- | --- |
| all | Composer 2.5 standard |

Never show third-party model names from the matrix.

## Third-party HITL (one turn)

Ask yes/no with prepaid-credit warning. Fable: also note Anthropic stores input/output for harm-prevention.
**да** → one `pool=paid` turn; next turn returns to Cursor matrix.
**нет** → Cursor matrix this turn.

## Subagent pins (only if user asked to spawn)

- `composer-2.5[fast=false]` or `inherit` when parent is Composer/Grok standard
- Never pass third-party model ids

## Handoff RU

После approve переключи чат на Composer 2.5 standard (не Fast) и выполни план пошагово.
План должен быть достаточно подробным для Composer (файлы, шаги, критерии done).

## Budget sync

```text
python <root>/scripts/sync_budget.py
```

`<root>` is `ORCHESTRATOR_ROOT.txt` or the directory that contains `SKILL.md`. Writes `<root>/config/budget.local.yaml` from the weekly Cursor-pool signal when the live payload confirms a field; otherwise `budget_source=unknown`. Chat: «синхронизируй бюджет» / `/budget sync`. Auth: Cursor `state.vscdb` or `CURSOR_SESSION_TOKEN`. Never print tokens.
