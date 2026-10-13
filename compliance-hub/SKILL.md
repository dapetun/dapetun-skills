---
name: compliance-hub
description: >-
  Unified compliance and legal screening for initiatives, NDAs, privacy/DPA,
  GDPR, EU AI Act, legal risk, document analysis, and Russian contract/website
  compliance. Use when the user asks for a compliance check, NDA triage, DPA/152-FZ
  review, GDPR handling, EU AI Act screening, legal risk, or RU legal website/contract
  review - especially when several of these would run together. Launches specialized
  subagent passes. Not legal advice.
---

# Compliance Hub

Один вход для compliance-проверок. Не делай всё в одном контексте - запускай **субагентов по ролям**, затем сведи вердикт. Это помощь юристу/себе, не замена counsel.

## Когда использовать

- запуск фичи / продукта / маркетинга с регуляторным риском
- входящий NDA
- обработка ПДн, DPA, трансграничная передача
- EU AI Act / риск-класс системы
- разбор юр. документа
- RU: договор / сайт (оферта, политика, 152-ФЗ)

## Роли (субагенты)

| Роль | Когда | Протокол |
| --- | --- | --- |
| `nda-triage` | Входящий NDA → GREEN/YELLOW/RED | `references/protocol-triage-nda.md` |
| `initiative-check` | Инициатива/фича → применимые режимы и approvals | `references/protocol-compliance-check.md` |
| `gdpr-data` | Обработка персональных данных (EU/общее) | `references/protocol-gdpr-data-handling.md` |
| `dpa-152` | DPA / ДОУ / 152-ФЗ | `references/protocol-dpa-review.md` |
| `eu-ai-act` | Системы ИИ под EU AI Act | `references/protocol-eu-ai-act-reviewer.md` |
| `legal-risk` | Оценка правовых рисков | `references/protocol-legal-risk-assessment.md` |
| `doc-analyze` | Разбор юр. документа | `references/protocol-legal-document-analyzer.md` |
| `ru-contract` | РФ договоры | `references/protocol-ru-legal-contract-review.md` |
| `ru-website` | РФ сайт / публичные документы | `references/protocol-ru-website-legal-compliance.md` |

Доп. файлы: `references/from-*/`.

## Оркестрация

1. Уточни объект (текст/файл/URL) и юрисдикции (RU / EU / US / mixed).
2. Выбери минимальный набор ролей; для «проверь всё» - параллельно релевантные.
3. Каждая роль - свежий субагент; не смешивай NDA-скептика с автором инициативы.
4. Сведи: короткая сводка (можно ли двигаться) → детали по ролям → открытые вопросы counsel.
5. Явно помечай: **не юридическая консультация**.

## Формат ответа

### Коротко
Вердикт: proceed / proceed with conditions / stop-and-counsel. Главные риски.

### Подробно
Таблица/блоки по ролям: findings, severity, что сделать до запуска.

## Замена старых скиллов

`triage-nda`, `compliance-check`, `gdpr-data-handling`, `dpa-review`, `eu-ai-act-reviewer`, `legal-risk-assessment`, `legal-document-analyzer`, `ru-legal-contract-review`, `ru-website-legal-compliance` считай устаревшими алиасами этого хаба (протоколы сохранены в `references/`).
