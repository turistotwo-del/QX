# QX 4.0.31 — тестовый отчёт

- Команда `python -m pytest -q`: 318 passed (20 subtests), 2 warnings.
- `tests/browser_smoke.py`: Browser E2E: OK (Chromium, Linux).
- `tests/browser_tz_multi_ai.py`: Browser multi TZ + AI review: OK (Chromium, Linux).
- `tests/browser_tz_ai_autofill.py`: Browser TZ AI safe auto-fill: OK (Chromium, Linux).
- Реальные модели не запускались: ответ AI в E2E замокан. Изменения проверены на безопасном контракте API и JSON, скорость реального Windows CPU не замерена.
- Макеты ТЗ (созданные для тестов): DOCX с перемешанными столбцами КТРУ, XLSX многолистовой, XLSX закупочная спецификация, TXT пары «характеристика: значение», ODT, длинный ТЗ, привязка отдельных позиций и отказ в автозаполнении неоднозначных полей.
- Не проходили QA: сканированные PDF без текстового слоя; старые бинарные DOC/XLS; реальные пользовательские нестандартные ТЗ; поведение Windows WebView2 / GGUF.
- Релиз кандидат; ставить поверх существующей версии рекомендуется через QuickFix с резервной копией папки QX.
