# Output contract

## Primary deliverable: human chat report

After `audit`, `plan`, `check`, `apply`, or `rollback`, the host agent writes a **human** message in the **user's language**:

1. **Short summary** (a few lines)
2. **Detailed explanation** (what it means, noise vs real issues, recommended next steps)

Full template: `references/chat-report.md`.

Raw CLI stdout / `audit-report.md` are **inputs for the host**, not the user-facing answer. Never dump ID lists or English jargon tables as the main reply unless the user explicitly asks for the machine report.

## Side artifacts (`--output` directory)

| File | Audience | Purpose |
| --- | --- | --- |
| `audit-report.md` | Host agent | Machine summary to translate into chat |
| `clusters.json` | Host agent | Candidates for semantic review |
| `semantic-findings.json` | Host agent → tool | Your semantic judgments (write this) |
| `findings.json` / `findings.static.json` | Power users | Full evidence |
| `optimization-plan.json` | Apply step | Recommendation IDs for `--only` |
| `inventory.json` | Catalog | What was discovered |
| `skill-graph.json` | Graph | Relations |
| `validation-report.json` | Metrics | Only trust values marked measured |
| `execution-manifest.json` | Apply | Last apply/rollback result |

Apply never runs unless the user confirms. Snapshots live under `<project>/.skill-optimizer/snapshots/`.
