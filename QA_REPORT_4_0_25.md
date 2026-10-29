# QX 4.0.25 — результаты проверки (22.10.2026)

**Автоматические тесты:**
- `python -m unittest discover -s tests -q`: 246/246 OK.
- `python -m unittest modern.test_modern modern.test_peripheral_choice modern.test_337_regression -q`: 27/27 OK.
- `python qx_entry.py --selfcheck`: OK.
- `python qx_entry.py --api-selfcheck`: OK.
- `python windows_build/release_metadata.py --check`: OK.
- `tsc -p modern/tsconfig.json`: OK.
- Отдельный Chromium E2E `browser_smoke.py`: OK (документ, подбор, закупка).
- Дополнительный Chromium E2E `browser_tz_multi_ai.py`: OK (сразу несколько файлов, третий ТЗ, сохранность ручной цены, переключение, просмотр, AI-предложения, подтверждение, .qxproj, удаление).
- Chromium regression suite — первые 5 сценариев прошли; полный прогон был прерван лимитом исполнения на старом сценарии `browser_eis_document_url.py`. Считать весь browser suite успешно пройденным нельзя.

**Отдельно протестировано в `test_tz_ai_multidoc.py`:**
- Разбор реальных DOCX-файлов и сохранение двух исходных документов в `.qxproj`.
- Режим реальной AI-интеграции с **симуляцией ответа локального Ollama**, валидация предложений и неподтверждённых значений; реальная LLM не запускалась.
- Корректная ошибка, когда вместо настоящей модели выбран офлайн-поиск.
- Отзывчивость UI/HTTP во время имитации медленного AI-инференса.

**Требуют проверки на компьютере с Windows:** первый переносной запуск и скачивание приватного Python; `ВКЛЮЧИТЬ_AI_GGUF.cmd`, совместимость wheel; модель Ollama/GGUF и качество её ответов на живых ТЗ; собственные DOCX/XLSX/PDF заказчика (особенно сканы); перенос пользовательских данных; поведение при внезапном отключении питания.

Сборка — честный *development* кандидат, без утверждений о сертифицированном Windows-релизе.
