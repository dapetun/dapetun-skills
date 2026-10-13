# dapetun-skills

Личная коллекция Agent Skills Даниила (`dapetun`). Установка:

```bash
npx skills add dapetun/dapetun-skills
```

Или один скилл:

```bash
npx skills add dapetun/dapetun-skills --skill skills-optimizer
npx skills add dapetun/dapetun-skills --skill github-discoverability
npx skills add dapetun/dapetun-skills --skill compliance-hub
npx skills add dapetun/dapetun-skills --skill evidence-check
```

## Skills in this repo

| Skill | Назначение |
| --- | --- |
| `skills-optimizer` | Аудит и безопасная оптимизация библиотеки Agent Skills |
| `github-discoverability` | Discoverability GitHub-репозиториев (README, topics, AI-cite) |
| `compliance-hub` | Единый compliance-вход (NDA, GDPR/DPA, EU AI Act, RU legal) через субагентов |
| `evidence-check` | Факты и цитаты: bib-audit / claim-source / draft-facts через субагентов |

На [skills.sh](https://skills.sh): после install telemetry страница репозитория обновляется автоматически.

## Dev (skills-optimizer package)

```bash
cd skills-optimizer
python -m venv .venv
pip install -e ".[dev]"
pytest
```
