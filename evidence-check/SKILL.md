---
name: evidence-check
description: >-
  Unified evidence and citation check for drafts and papers. Use when the user
  asks to fact-check, verify citations, audit a bibliography, check claim-to-source
  support, catch fake or wrong-context references, or run the full citation/fact
  stack. Replaces separate citation-audit, citation-verification,
  claim-source-verification, and fact-check skills by launching specialized
  subagent passes.
---

# Evidence Check

Один вход для проверок фактов и цитат. Не делай всё сам в одном контексте - запускай **параллельные субагенты** по ролям ниже, затем сведи вердикт.

## Когда использовать

- фактчек черновика (pitch, PR, комментарий, статья)
- проверка библиографии / `\cite` / DOI / авторов
- claim → source: правда ли источник поддерживает утверждение
- перед сабмитом / отправкой текста

Не для открытого исследования темы с нуля (`research`) и не для поиска публичных API.

## Роли (субагенты)

Запускай через Task/subagent. Каждая роль - **свежий контекст**. Не давай скептику читать рассуждения предлагающего.

| Роль | Что делает | Протокол |
| --- | --- | --- |
| `bib-audit` | Существование записи, метаданные, wrong-context cite | `references/bib-audit-protocol.md` |
| `claim-source` | Поддерживает ли источник утверждение (adversarial) | `references/claim-source-protocol.md`, `references/adversarial-protocol.md` |
| `draft-facts` | Фактчек утверждений уже в черновике | `references/draft-fact-check-protocol.md` |
| `cite-practices` | Правила/типичные ошибки цитирования (справочник) | `references/citation-practices-guide.md`, `references/verification-rules.md` |

Дополнительно: `references/rejection-taxonomy.md`, `references/common-errors.md`, скрипты в `references/from-citation-verification/scripts/` при необходимости.

## Оркестрация

1. Уточни объект: черновик / paper+bib / список claim→source.
2. Выбери минимальный набор ролей:
   - только черновик без библиографии → `draft-facts`
   - paper + bib → `bib-audit` + `claim-source` (на спорных cites)
   - «проверь всё» → все четыре (cite-practices можно кратко, без отдельного тяжёлого агента)
3. Запусти роли **параллельно**, где независимо.
4. Сведи ответ пользователю: сначала короткая сводка, затем детали по ролям (провалы первыми).
5. Не мутируй `.bib` / текст без явного разрешения.

## Формат итога

### Коротко
Сколько проверено, сколько провалов, главный риск.

### Подробно
По ролям: что проверяли, вердикты, что чинить. Без сырого JSON, если пользователь не просил.

## Важно

Старые скиллы `citation-audit`, `citation-verification`, `claim-source-verification`, `fact-check` заменены этим. Если они ещё лежат в библиотеке - считай их устаревшими алиасами и предпочитай `evidence-check`.
