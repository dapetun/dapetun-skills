# Agent prompt: improve cursor-hindsight-ondemand coherence + discoverability

Copy the block below into a new agent chat with the **cursor-hindsight-ondemand** repo open.

---

```text
Ты работаешь в репозитории https://github.com/dapetun/cursor-hindsight-ondemand (локальный клон).

Контекст: парный MIT-проект https://github.com/dapetun/cursor-model-orchestrator уже обновлён (public, README с What/FAQ/core vs stack, llms.txt, GitHub description/topics/homepage → этот репо, release v0.1.0). Этот репо = lifecycle локального Hindsight; orchestrator = model router. Канон: MCP server name `hindsight`, API `http://127.0.0.1:9077`, порядок stack: orchestrator -Profile stack → этот install.ps1 → GitNexus optional.

Задача: улучшить согласованность и discoverability (SEO/AI-SEO для GitHub), НЕ дублируя skill orchestrator и НЕ добавляя GitNexus.

Сделай:

1. GitHub metadata (gh):
   - description: коротко EN, упомяни on-demand Hindsight + localhost + stack partner cursor-model-orchestrator (если ещё не так).
   - homepage: https://github.com/dapetun/cursor-model-orchestrator
   - topics: сохрани существующие; добавь недостающие связки, например `cursor-model-orchestrator` / `model-router` если допустимы; не раздувай >15.
   - Убедись, что репо public.

2. README (EN + RU):
   - В начале: «Last updated: YYYY-MM-DD» и ссылка на парный orchestrator release/README.
   - Выровняй таблицу What you get: если examples/mcp.json вызывает `mcp-launch.mjs`, не пиши только `mcp-launch.ps1` без пояснения (ps1 vs mjs).
   - FAQ: одна строка «Do I need cursor-model-orchestrator?» → No for memory-only; Yes for stack retain from the router skill.
   - Не ослабляй раздел Used with Cursor Model Orchestrator (stack profile).

3. llms.txt:
   - Укажи, что partner orchestrator теперь public; ссылки на его README / docs/integrations/stack.md / llms.txt.
   - Канон MCP `hindsight` + URL 127.0.0.1:9077.

4. docs/INTEGRATIONS.md:
   - Проверь зеркальность с orchestrator docs/integrations/stack.md (порядок install, имена, soft-dep).
   - Добавь Last updated при правках.

5. Release (если ещё нет симметричного тега):
   - Создай GitHub Release (например v1.0.0 или v0.1.0) с notes: lifecycle-only, stack partner link, MCP name hindsight.
   - Не ломай MIT / NOTICE.

6. Sanity:
   - Нет абсолютных личных путей в examples (только YOU / placeholders).
   - Не коммить секреты.
   - Коммит + push на main.

Критерии готово: анонимно открывается README; description/topics/homepage согласованы с orchestrator; README/llms/INTEGRATIONS без противоречий ps1/mjs и с явным partner link; есть release tag; install order совпадает с orchestrator stack.md.
```
