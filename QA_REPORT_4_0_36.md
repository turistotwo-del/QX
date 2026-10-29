# QX 4.0.36 — отчёт о проверках

Дата: 23.10.2026

- `python -m pytest -q`: **355 passed**, 25 subtests passed, 2 DeprecationWarning внешних библиотек.
- `tsc --noEmit -p modern/tsconfig.json`: успешно.
- `node --check modern/web/app.js`: успешно.
- `PYTHONPATH=.:tests python tests/browser_contracts_4036.py`: **BROWSER_CONTRACTS_4036_OK**.
- `PYTHONPATH=.:tests python tests/browser_smoke.py`: **Browser E2E: OK**.
- `PYTHONPATH=.:tests python tests/browser_quick_notes_4035.py`: **BROWSER_QUICK_NOTES_4035_OK**.
- `PYTHONPATH=.:tests python tests/browser_delete_tender.py`: **BROWSER_DELETE_TENDER_OK**.
- `PYTHONPATH=.:tests python tests/browser_save_4033.py`: **Browser export native save, download fallback, cancel: OK**.

Новые модульные сценарии: привязка `.qxproj` и идемпотентность, сохранение вложения в резервной копии и проверка целостности, безопасное автозаполнение незаполненных полей, запрет перезаписи пользовательской гарантии, противоречащие условия, защита от выдуманного AI адреса, проверка времени аукциона и напоминаний за 60 и 15 минут.

Браузерный сценарий 4.0.36 использует воспроизводимые тестовые данные и подменённые документы. Он подтверждает интерфейс, но **не подтверждает фактическую работу локальной модели на Windows** и не измеряет реальную скорость анализа больших договоров. Отдельные системные уведомления Windows также не запускались в этой Linux-среде.
