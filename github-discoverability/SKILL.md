---
name: github-discoverability
description: >-
  Optimize discoverability of GitHub repositories (not marketing websites): README
  as landing page, About/topics/social preview, releases, docs structure, and
  agent/AI citation readiness (llms.txt, clear capability claims). Use when the
  user asks to improve GitHub SEO, repo discoverability, README for stars/search,
  topics, or make a repo easier for humans and LLMs to find and cite. Replaces
  separate seo / seo-audit / ai-seo / content-strategy for repo work.
---

# GitHub Discoverability

Один вход для «SEO репозитория». Не оптимизируй лендинги и блоги - цель: **GitHub repo** (поиск GitHub, Google по README, упоминания в AI-ответах).

## Когда использовать

- «сделай README нормальным / продающим для GitHub»
- topics, About, social preview, badges
- почему репо не находят / плохо цитируют
- подготовка `llms.txt` / agent-readable docs в репо
- аудит нескольких репозиториев автора

Не для: классического SEO сайта, Core Web Vitals страницы, контент-календаря блога.

## Роли (субагенты)

Запускай через Task/subagent. Свежий контекст на роль. Параллель, где независимо.

| Роль | Фокус | Опора |
| --- | --- | --- |
| `readme-landing` | Структура README: проблема → решение → quickstart → proof → links | `references/` + лучшие практики GitHub |
| `metadata` | About blurb, topics (5–20), website, social preview image | GitHub UI fields |
| `search-signals` | Имя репо, описание, keywords в README H1/H2, releases/changelog | GitHub Search + Google indexing of README |
| `ai-cite` | Как LLM находит и цитирует репо: ясная capability, llms.txt, docs map | идеи из бывшего `ai-seo` в `references/from-ai-seo/` |
| `audit` | Чеклист здоровья discoverability + приоритетный diff | бывший `seo-audit` mindset, но под репо |

Доп. материалы: `references/from-seo/`, `references/from-seo-audit/`, `references/from-ai-seo/` (если скопированы).

## Оркестрация

1. Уточни репо (path или `owner/name`) и цель (stars / hiring / academic cite / tool adoption).
2. Минимальный набор:
   - быстрый чек → `audit` + `metadata`
   - «переписать README» → `readme-landing` + `search-signals`
   - «чтобы AI находили» → `ai-cite` + `readme-landing`
   - полный прогон → все роли
3. Сведи ответ: короткая сводка → подробный план правок (что менять в каких файлах).
4. Не пушь и не меняй remote settings без явного OK.

## Формат ответа

### Коротко
Главные дыры discoverability и 1–3 главных фикса.

### Подробно
По ролям: findings + конкретные правки (текст About, список topics, outline README, llms.txt draft).

## Замена старых скиллов

`seo`, `seo-audit`, `ai-seo`, `content-strategy` для работы с **репозиториями** считай устаревшими алиасами этого скилла. Для маркетингового SEO сайта этот скилл не предназначен.
