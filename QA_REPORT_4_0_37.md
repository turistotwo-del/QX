# QX 4.0.37 — проверки

- Модульный набор: 330 пройденных тестов, 18 дополнительных проверок (tests/, кроме tests/test_browser_runner.py).
- Новый тест календаря заметок и котировок: 4/4 — API, SQLite, напоминания и редактирование статусов.
- Playwright/Chromium: browser_calendar_quotes_4037.py — PASS, открытие задачи, завершение, итоги котировки, отсутствие аукциона.
- Playwright/Chromium: browser_quick_notes_4035.py — PASS; browser_contracts_4036.py — PASS.
- browser_tender_4034.py завис при завершении сценария. По диагностическому выводу данные получены, но тест не считался завершённым успешно.
- tests/test_browser_runner.py отдельно показал нестабильный результат и не включён в число 330; это тест инфраструктуры запуска браузера.
- Node.js --check modern/web/app.js — PASS; compileall modern — PASS.
- Windows desktop/notifications не проверены на Windows.
