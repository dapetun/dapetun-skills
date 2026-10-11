# Output contract

After `audit --phase static` / `merge`, look in the `--output` directory:

| File | Audience | Purpose |
| --- | --- | --- |
| `audit-report.md` | Human | Start here: **Top actions** |
| `clusters.json` | Host agent | Candidates for semantic review |
| `semantic-findings.json` | Host agent → tool | Your semantic judgments (write this) |
| `findings.json` / `findings.static.json` | Power users | Full evidence |
| `optimization-plan.json` | Apply step | Recommendation IDs for `--only` |
| `inventory.json` | Catalog | What was discovered |
| `skill-graph.json` | Graph | Relations |
| `validation-report.json` | Metrics | Only trust values marked measured |

Apply never runs unless the user confirms. Snapshots live under `<project>/.skill-optimizer/snapshots/`.
