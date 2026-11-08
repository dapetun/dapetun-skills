---
name: model-orchestrator
description: >
  Always-on cost-aware model router for Cursor. Classifies each user prompt with
  deterministic rules (keywords + project type), recommends only included Cursor
  models (Composer 2.5 standard, Grok 4.7 standard, Auto Cost) under the weekly
  Cursor-models pool, and prints a short Russian [route] line. Doctrine: Grok
  plans/analyzes hard work; Composer executes code and file ops. Third-party
  models need one-turn HITL. Works standalone (core profile). With stack
  profile, lean-logs to Hindsight when MCP is available and may hint GitNexus
  on coding tasks. Use on coding, DS/ML, academic papers, research, frontend,
  and whenever the user mentions /eco, /max, or /route.
---

# Model Orchestrator (v1 — Cursor models only)

## Mission

Protect the **weekly Cursor models pool** (Composer 2.5, Grok 4.7 / 4.6 / 4.5;
shared with Grok Bot and Grok apps) from Fast-tier burn and from third-party
prepaid credit.

**Grok 4.7 standard** **plans / analyzes** hard work.
**Composer 2.5 standard** **executes** (read files, write/edit code, routine tools).
**Auto Cost** covers routine when the plan offers Auto (Plus has no Auto → Composer).

Overlay on Auto Cost; do not recommend Balance / Intelligence (Teams/Enterprise
only; may route to third-party).

User-facing language: **Russian**. This skill's instructions: **English**.

## Doctrine: planner → executor (Cursor pool)

Canonical source: `doctrine` + `phases` in `routes.yaml`.

| Role (`роль=`) | Who | Does |
| --- | --- | --- |
| `план` | Grok 4.7 standard (eco → Composer) | Detailed plan, specs, architecture |
| `код` | Composer 2.5 standard | File reads/writes, patches, routine agent work |
| `анализ` | Grok 4.7 standard (eco → Composer) | Interpret results / write prose — **not** code edits |

**Hard rules:**

- Never put Claude, GPT, Gemini, Muse, Fable, or other third-party models in the
  routing matrix.
- Never recommend Fast or Grok 500k unless the user explicitly asked.
- Never recommend third-party for writing code. If the user asks to implement
  now, set `роль=код` and recommend Composer 2.5 standard (не Fast).

### Phase detection (after tier)

1. Explicit Cursor pin («только Composer», «Grok», named Cursor model) wins;
   still prefer **standard** unless they asked Fast / 500k.
2. Explicit **third-party** pin or paid phrase → **HITL** (see below); do not
   continue the matrix until yes/no.
3. `force_execute_if` keywords → `роль=код` → use `executor_logical[mode]`.
4. `force_plan_if` keywords → `роль=план` → use `logical_model[mode]`.
5. Else if tier in `always_execute_tiers` → `роль=код`.
6. Else if tier in `default_plan_tiers` and no approved plan in thread → `роль=план`.
7. Else if tier in `analyze_tiers` and prompt is Q&A (no «напиши код» / «реализуй») → `роль=анализ`.
8. Else if user said «реализуй» / approved a prior plan → `роль=код`.

### Planner output contract (when `роль=план`)

Plan must be **Composer-ready** in Russian (or bilingual if user asks EN):

- Goal + non-goals
- Files to touch (paths)
- Ordered steps (small enough for one Composer turn each if long)
- Acceptance / done criteria
- Risks / what not to change
- End with handoff from `doctrine.handoff_ru`

Do **not** apply file edits while recommending Grok as the chat model for plan.

### Executor handoff (`роль=код`)

In `действие`: «переключи на Composer 2.5 standard (не Fast) и выполни план».
If no plan exists yet on a hard tier, first recommend `роль=план` unless user forced execute.

### Subagents (spawn still off by default)

Recommend-only: do **not** spawn. If the user explicitly asks to spawn:

- Pin `composer-2.5[fast=false]`, or `inherit` when the parent is already on
  Composer / Grok standard.
- Never pass a third-party model id to Task (bills prepaid credit even if the
  picker shows Auto / Grok / Composer).

## Config locations

Resolve the orchestrator **root** in this order:

1. Path in `ORCHESTRATOR_ROOT.txt` next to this SKILL.md, when that file exists (`install_skill.ps1` writes it and points at a full clone).
2. The directory that contains this SKILL.md, when `config/routes.yaml` is beside it. `npx skills add` ships this bundle: `config/` plus `scripts/sync_budget.py`.
3. The open workspace, when that workspace contains `config/routes.yaml`.

Read from `<root>/config/`: `routes.yaml`, `integrations.yaml`, `projects.yaml`, `budget.yaml`, `budget.local.yaml` (synced), `models.generated.yaml`.

If `<root>/config/integrations.yaml` is missing, use `integrations.yaml` next to this SKILL.md when present. If `routes.yaml` is missing, use the embedded fallbacks in [reference-routes.md](reference-routes.md).

If `projects.yaml` is missing, use `projects.example.yaml` markers only (path_prefixes may be placeholders).

### Integrations profile (`integrations.yaml`)

| `profile` | Behavior |
| --- | --- |
| `core` (default) | Router only. Skip Hindsight retain and GitNexus hints. |
| `stack` | Soft deps: retain if Hindsight MCP available; optional GitNexus hint on coding tiers. |

Read `hindsight.enabled` / `gitnexus.enabled` from that file. Missing file → treat as **core**.

## Every turn (mandatory)

1. **Classify once** (mode + project_type + tier + **phase/role** + logical model + pool + budget + shape).
2. Print **one** Russian `[route]` block at the start of the reply (before plan). Machine fields `tier`, `model`, `mode`, `pool`, `budget`, `shape`, `роль` are required every turn.
3. **Integrations (soft):** Hindsight retain and GitNexus hints — see below. Never fail the turn if tools are absent.
4. Continue per role: planner elaborates; executor implements after approve / model switch.
5. Do not spawn subagents; tell the user to switch the chat model if needed. Plan-shape / splitter text is a hint only.

### Route line format (Russian)

```text
[route] project=<type> tier=<tier> model=<display> mode=<eco|balance|max> pool=<cursor|paid> budget=<ok|warn|exhausted|unknown> shape=<none|mapper|specialist|pipeline|hybrid> роль=<план|код|анализ>
почему: <≤120 chars>
действие: <переключи модель чата на … · план → approve · handoff на Composer standard · optional shape/roles hint>
```

- `pool`: `cursor` for matrix routes; `paid` only after HITL yes on a third-party pin (one turn).
- `budget`: `ok` if remaining OK and under warn ratio; `warn` at hard-block@warn_ratio; `exhausted` if pool spent; `unknown` if sync has no confirmed weekly-pool field.
- `shape`: from `plan_shapes.by_tier` in `routes.yaml` (default `none`). If `shape != none` and `splitter_hint: true`, add one RU hint in `действие` naming roles that *would* fire — **never spawn**.
- `роль`: `план` | `код` | `анализ` (see doctrine).
- `model`: for `план`/`анализ` use `logical_model[mode]`; for `код` use `executor_logical[mode]` when present, else Composer standard. Display names must say **standard / не Fast** when recommending Composer or Grok.

If `/route` only: print the block and **stop**.

## Precedence (highest wins)

1. Explicit **third-party** pin or paid override → HITL (one turn if yes)
2. Explicit Cursor model pin («только Composer», «Grok», named Cursor model) — still standard unless Fast/500k asked
3. Slash mode `/eco` or `/max` (sets mode; still classify tier)
4. Prompt tags `@ds` `@paper` `@web`
5. `projects.yaml` path prefix / path_contains
6. Repo marker heuristics from `projects.yaml`
7. Keyword classifier (see below)
8. Default → `default_code` / Auto Cost overlay

## Modes

| Mode | Behavior |
| --- | --- |
| `eco` | Composer 2.5 standard only (all tiers). Stretches the weekly pool. |
| `balance` | Default. Auto Cost / Composer for routine; Grok standard for hard plan/analyze; Composer for code. |
| `max` | Grok 4.7 standard for hard plan **and** heavy execute. Still no Fast, no third-party. |

Detect `/eco` `/max` in the user message. Default mode = `balance`.

## Budget guard (sync + policy)

**Policy** (thresholds): `<root>/config/budget.yaml` — `warn_at_ratio`, `sync_ttl_minutes`, weekly-pool notes.

**Live spend** (preferred): `<root>/config/budget.local.yaml` from `python <root>/scripts/sync_budget.py`. Prefer a confirmed **weekly Cursor-pool** percent field. Never print the session token, and never put it in `[route]` or Hindsight.

### Before classify (each turn)

1. If user says «синхронизируй бюджет» or `/budget sync` → run sync with force (ignore TTL).
2. Else if `budget.local.yaml` missing **or** `synced_at` older than `sync_ttl_minutes` (default 60) → run:
   `python <root>/scripts/sync_budget.py` (cwd = orchestrator root). Soft-fail if the script is missing or it errors.
3. Resolve spend:
   - **Synced/fresh local with confirmed pool field:** `spent_ratio` from that field / 100.
   - **Stale local** (sync failed, file kept): use last local values; mention `budget_source=stale` in `почему`.
   - **No confirmed field / `spend_field: unknown`:** `budget=unknown`; do **not** block hard tiers using legacy `api_percent_used` as if it were the weekly pool.
4. Never log or retain session tokens. Never put tokens in `[route]` or Hindsight.

### Guard rules

- **Composer-only triggers:** pool exhausted, mode `/eco`, or `spent_ratio >= warn_at_ratio` without paid HITL override.
- On those triggers: resolve **`logical_model.eco`** / `exhausted_policy.matrix` — Composer standard only.
- Hard tiers: `science_stats`, `refactor_architecture`, `long_agent`, `parallel_roles`, `paper`, `frontend_design`.

### Exhausted / eco matrix (bind to YAML)

| Tier | Model | Warning |
| --- | --- | --- |
| quick_edit, research_docs, cursor_meta, docs_office, default_code | Composer 2.5 standard | docs_office academic → paper row |
| frontend_design, paper, science_stats, refactor_architecture, long_agent | Composer 2.5 standard | use `exhausted_policy.warnings_ru` |
| parallel_roles | `role_map_exhausted` | all roles → Composer |

**Mandatory RU for science_stats on eco / tight pool** (in `почему` / `действие`):

```text
Недельный пул Cursor / eco — ответ на Composer 2.5 standard. Перепроверь цифры и выводы.
```

**Display:** `mode=eco` and/or `budget=warn|exhausted|unknown` + `pool=cursor` + Cursor display name only (matrix).

## Plan shapes (hints only)

Read `plan_shapes` from `routes.yaml`. Defaults if missing: `shape=none`, no spawn.

| Tier (examples) | shape | Splitter hint (RU, do not spawn) |
| --- | --- | --- |
| parallel_roles | specialist | роли: planner/coder/reviewer/… — не спавню |
| refactor_architecture | pipeline | роли: planner→coder→reviewer→verifier — не спавню |
| long_agent | hybrid | роли: planner→coder→reviewer — не спавню |
| science_stats, quick_edit, … | none | (omit roles line) |

## HITL — third-party / paid (one turn)

**Never** recommend or run a third-party model from the matrix.

When the user **explicitly** names a third-party model (Claude / GPT / Gemini / Muse / Fable / …)
or says «разреши дорогие модели» / `/max force`:

1. Ask yes/no with `hitl.confirm_prompt_ru` (add `confirm_prompt_fable_extra_ru` for Fable).
2. **да** → one turn only: `pool=paid`, named model in `model=`, then next turn returns to the Cursor matrix.
3. **нет** → fall back to the Cursor matrix for this turn.

Do not silently map a third-party name onto Composer/Grok.

## Project type

Types: `ds` | `paper` | `web` | `backend` | `cursor_meta` | `mixed`.

Apply `project_type_nudges` from `routes.yaml` after tier classification (bias, do not erase a higher-severity science/refactor match).

### Markers (summary)

- `ds`: notebooks, pandas/sklearn/torch, data/ml dirs
- `paper`: Magister/статья/ВКР text paths, `.tex`, md-heavy without app layout
- `web`: `package.json`, tsx/jsx app dirs
- `cursor_meta`: this skill/repo, `.cursor/`, `SKILL.md`, `mcp.json`

## Tier classifier (rules)

Score keywords (RU+EN). If several match, pick **highest severity**:

`science_stats` > `refactor_architecture` > `long_agent` > `parallel_roles` > `paper` > `frontend_design` > `docs_office` > `research_docs` > `cursor_meta` > `default_code` > `quick_edit`

### Keyword seeds

**science_stats:** p-value, p value, регресси, эконометр, прогноз, гипотез, panel, DID, значимост, std\.?err, SE\b, statsmodels, коэффициент, выборк, causal, ATE, MLM, фиксированн.*эффект

**refactor_architecture:** рефактор, архитектур, multi-file, многофайл, redesign, разнеси модул, перестрой

**long_agent:** 30\+?\s*мин, долг(ая|ий) сесс, сделай всё, end-to-end всё, длинн(ый|ая) агент

**parallel_roles:** нескольк.*агент, субагент, best-of-n, parallel agents, reviewer и coder

**paper:** статья, ВКР, рецензент, журнал, абзац, раздел статьи, диплом

**frontend_design:** UI, UX, CSS, Figma, лендинг, landing, сделай красив, layout, хедер, hero

**docs_office:** \.docx|\.pptx|\.xlsx|\.pdf|ворд|powerpoint|excel

**research_docs:** сравни библиотек, documentation, найди в docs, research

**cursor_meta:** skill, MCP, orchestrator, \.cursor/rules, user rule

**quick_edit:** поправь, переименуй, typo, опечатк, одну строк, tiny fix — only if no higher tier matched

**Negations:** if prompt contains «не трогай статистику» / «без регрессии» / «не про p-value», do not count science_stats hits for those tokens.

### Mixed concerns

If prompt clearly combines paper + stats + code (or similar):

- State that decomposition is recommended; list 2–3 role routes; pick the **highest severity** tier for the primary `[route]` line.
- Plan/analyze on Grok; code path always Composer.

### Resolve logical → display

Map through `models.generated.yaml` `logical.*.display` (first available candidate):

- `роль=план|анализ` → `logical_model[mode]`
- `роль=код` → `executor_logical[mode]` if present, else Composer standard

Append **standard / не Fast** in `действие` for Composer and Grok recommendations.

Science/stats **analyze** when pool OK: prefer Grok, not Composer-only. Science/stats **code**: plan on Grok, execute on Composer. Eco / tight pool: Composer + mandatory science warning.

## Hindsight logging (anti-spam, stack only)

**Gate:** `integrations.yaml` has `hindsight.enabled: true` **and** Hindsight MCP/tools are available (typically via [cursor-hindsight-ondemand](https://github.com/dapetun/cursor-hindsight-ondemand), MCP server name `hindsight` unless overridden).

- If gate fails (core profile, or MCP down): **skip retain** — do not error, do not claim logging in `[route]`.
- If gate passes: call `retain` **only if** the tuple `(task_type, model, mode, project_type, pool, budget, shape, роль)` differs from the last one logged **in this chat**.

Content template (English keys OK inside text):

```text
orchestrator_route task_type=<tier> tier=<tier> model=<display> logical=<key> reason=<why≤120> mode=<mode> project_type=<type> pool=<cursor|paid> budget=<ok|warn|exhausted|unknown> shape=<none|mapper|specialist|pipeline|hybrid> role=<plan|execute|analyze>
```

- `document_id`: `cursor-model-orchestrator-route-log-YYYY-MM` (UTC month)
- **Do not** log full prompts, code, token counts, stack traces, or PII
- Schema details: repo `docs/hindsight-schema.md` (used when stack + Hindsight)

## GitNexus hint (soft, stack only)

**Gate:** `gitnexus.enabled: true` and GitNexus MCP/CLI available.

On coding-related tiers (`default_code`, `refactor_architecture`, `long_agent`, `cursor_meta` when editing code): one short hint that impact / `detect_changes` is available — **do not** block classify/route if GitNexus is missing. Never require GitNexus in core.

## Slash commands

- `/eco` — force eco mode for this turn
- `/max` — force max mode for this turn (Grok standard on hard work; still no third-party)
- `/route` — classify, print `[route]`, stop
- `/max force` — paid-override phrase → HITL for one third-party turn (not a silent matrix upgrade)
- `/budget sync` — run `python <root>/scripts/sync_budget.py` then classify (or stop after sync if user only asked sync)

## Hard rules

1. Never select a third-party model without HITL confirmation; yes = one turn only.
2. Never recommend Fast or Grok 500k unless the user asked.
3. Never recommend third-party models from the matrix, including in `/eco` or when budget is exhausted/unknown.
4. Never skip the Russian `[route]` line (include `роль=`).
5. Prefer synced `budget.local.yaml`; refresh when stale; never expose Cursor session tokens.
6. Recommend only — no cascade execution, no best-of-N runs, no mid-chat model mutation, no subagent spawn (shape/splitter are hints).
7. Prefer plan → approve → Composer execute before large edits.
8. Bash is not a separate tier; route like normal code (executor = Composer standard).

## Embedded fallback (if YAML missing)

- eco / tight pool → Composer 2.5 standard (не Fast)
- routine balance → Auto Cost, else Composer 2.5 standard
- science_stats / paper / refactor / long_agent **plan|анализ** (pool OK) → Grok 4.7 standard
- same tiers **код** → Composer 2.5 standard
- max hard plan/execute → Grok 4.7 standard (не Fast, не xhigh as a price lever)
- third-party name → ask yes/no for one paid turn
