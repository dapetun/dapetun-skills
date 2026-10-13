# Reference routes (cheat sheet)

Use when YAML configs are unavailable. Prefer `config/routes.yaml` when present.

## Doctrine (v0.2)

**Other Models plan / analyze. Composer or Grok execute code and file ops.**
Never recommend Other for writing code.

| роль | Typical model (balance, budget OK) |
| --- | --- |
| план | Sonnet / Opus / Sol by tier |
| код | Composer 2.5 (UI → Grok 4.7) |
| анализ | Sonnet / Opus (science, paper Q&A) |

## [route] machine fields (v0.2)

```text
[route] project=… tier=… model=… mode=… pool=… budget=… shape=… роль=<план|код|анализ>
```

| Field | Values |
| --- | --- |
| pool | `cursor` \| `other` \| `mixed` |
| budget | `ok` \| `warn` \| `exhausted` |
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

- `eco` → Cursor pool only (Composer 2.5 / Grok 4.7 per tier)
- `balance` → Auto/Composer execute; escalate plan/analyze to Other
- `max` → stronger Other **planners** if budget allows; execute still Composer/Grok

## Tier → model (balance / budget OK)

| Tier | роль=план / анализ | роль=код |
| --- | --- | --- |
| quick_edit | — | Auto / Composer 2.5 |
| default_code | — | Auto / Composer 2.5 |
| research_docs | Auto / Composer (or analyze on Sonnet if deep) | Composer 2.5 |
| cursor_meta | — | Composer 2.5 |
| docs_office | Sonnet if academic prose | Composer 2.5 |
| frontend_design | Claude Sonnet 5 | Grok 4.7 |
| paper | Claude Sonnet 5 | Composer if tooling code |
| science_stats | Claude Sonnet 5 (Q&A) | Composer 2.5 (implement) |
| refactor_architecture | Claude Opus 5 | Composer 2.5 |
| long_agent | Claude Opus 5 | Composer 2.5 |
| parallel_roles | advise role map | coder = Composer |

## max mode upgrades (planners only)

- science_stats / paper → Claude Opus 5
- refactor / long_agent → GPT-5.6 Sol or Claude Opus 5
- execute path unchanged (Composer / Grok)

## eco / exhausted / hard-block (shared Cursor-only matrix)

Triggers: `/eco`, `remaining_usd<=0`, hard-block@80% without override.

| Tier | Model |
| --- | --- |
| quick_edit | Composer 2.5 |
| default_code | Auto / Composer 2.5 |
| research_docs | Composer 2.5 |
| cursor_meta | Composer 2.5 |
| docs_office | Composer 2.5 (academic → paper) |
| frontend_design | Grok 4.7 |
| paper | Grok 4.7 (+ warning) |
| science_stats | Grok 4.7 (+ **mandatory** science warning) |
| refactor_architecture | Grok 4.7 |
| long_agent | Grok 4.7 |
| parallel_roles | role_map_exhausted |

### role_map (budget OK)

| Role | Model |
| --- | --- |
| planner | Claude Opus 5 |
| coder | Composer 2.5 |
| reviewer | Claude Sonnet 5 |
| researcher | GPT-5.6 Terra |
| verifier | Grok 4.7 |
| scientist | Claude Opus 5 |

### role_map_exhausted

| Role | Model |
| --- | --- |
| planner | Grok 4.7 |
| coder | Composer 2.5 |
| reviewer | Grok 4.7 |
| researcher | Grok 4.7 |
| verifier | Grok 4.7 |
| scientist | Grok 4.7 |

Never show Other model names while Cursor-only.

## Fable

Never without Russian HITL confirm.

## Handoff RU

После approve переключи чат на Composer 2.5 и выполни план пошагово.
План должен быть достаточно подробным для Composer (файлы, шаги, критерии done).

## Budget sync

```text
python <root>/scripts/sync_budget.py
```

`<root>` is `ORCHESTRATOR_ROOT.txt` or the directory that contains `SKILL.md`. Writes `<root>/config/budget.local.yaml` (`api_percent_used` = Other Models). Chat: «синхронизируй бюджет» / `/budget sync`. Auth: Cursor `state.vscdb` or `CURSOR_SESSION_TOKEN`. Never print tokens.
