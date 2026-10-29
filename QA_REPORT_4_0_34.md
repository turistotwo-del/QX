# Проверка QX 4.0.34

- TypeScript: `tsc -p modern/tsconfig.json` — OK
- JS: `node --check modern/web/app.js` — OK
- `pytest tests/` — 317 passed; 18 subtests passed; 2 предупреждения об устаревших API
- Chromium E2E `tests/browser_tender_4034.py` — OK (галочка выключена → не создаёт закупку; ручная привязка; mock XML; срок подачи и календарь; форматирование)
- Chromium E2E `tests/browser_smoke.py` — OK (адаптирован к новому opt-in)
- Chromium E2E `tests/browser_delete_tender.py` — OK
- Chromium E2E `tests/browser_save_4033.py` — OK
- Изолированные тесты миграции SQLite и безопасности ЕИС — OK
- Прямой доступ к настоящему ЕИС, реальное выполнение Qwen и запуск установщика Windows — не проверены
