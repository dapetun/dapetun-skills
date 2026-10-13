# Chat report format (mandatory)

Speak in the **same language the user is using** in this conversation (Russian if they write Russian, English if English, etc.).

Do **not** paste raw CLI stdout, long recommendation ID lists, skill_id hashes, or jargon tables as the main answer.

## Structure (always both parts)

### 1. Short summary (3–6 lines max)

Plain language. What we found and what matters. No IDs unless the user asked for them.

Example (RU):

> Проверил 76 скиллов. Реальных проблем мало: один скилл стоит дважды, старая копия оптимизатора мешает новой, плюс много ложных срабатываний парсера. Массово ничего чинить не надо - нужны точечные решения.

### 2. Detailed explanation

Same language. Explain *what it means*, *why it matters*, *what is noise*, *what you recommend next*. Use skill **names**, not internal IDs. Offer choices; do not apply until the user confirms.

Suggested subsections (adapt freely):

- Что реально не так
- Что похоже на шум / ложные срабатывания
- Что можно сделать (варианты)
- Что я пока не трогал

## After apply / rollback

Same two-part format: short outcome, then what changed and how to undo if needed.

## Machine artifacts

Keep using JSON/MD under `--output` for your own next steps (`--only`, rollback). Those files are for you, not for the user-facing message.
