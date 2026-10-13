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
npx skills add dapetun/dapetun-skills --skill model-orchestrator
npx skills add dapetun/dapetun-skills --skill public-api-discovery
```

## Skills in this repo

| Skill | Назначение |
| --- | --- |
| `skills-optimizer` | Аудит и безопасная оптимизация библиотеки Agent Skills |
| `github-discoverability` | Discoverability GitHub-репозиториев (README, topics, AI-cite) |
| `compliance-hub` | Единый compliance-вход (NDA, GDPR/DPA, EU AI Act, RU legal) через субагентов |
| `evidence-check` | Факты и цитаты: bib-audit / claim-source / draft-facts через субагентов |
| `model-orchestrator` | Маршрутизация моделей Cursor (tier / budget / `[route]`) |
| `public-api-discovery` | Поиск публичных API без ключей и с понятными лимитами |

На [skills.sh](https://skills.sh): после install telemetry страница репозитория обновляется автоматически.

`model-orchestrator` раньше жил в отдельном репо `dapetun/cursor-model-orchestrator` — канон теперь здесь. Локальный install с `ORCHESTRATOR_ROOT`:

```powershell
cd model-orchestrator
.\scripts\install_skill.ps1
```

## Dev (skills-optimizer package)

```bash
cd skills-optimizer
python -m venv .venv
pip install -e ".[dev]"
pytest
```
