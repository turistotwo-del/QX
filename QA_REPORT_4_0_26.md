# QX 4.0.26 — отчёт о проверках (22.10.2026)

## Проверено

- `python -m unittest discover -s tests -q` — **253/253 PASS**, включая 7 новых тестов автоматической установки AI.
- `python -m unittest modern.test_modern modern.test_peripheral_choice modern.test_337_regression -q` — **27/27 PASS**.
- `python qx_entry.py --selfcheck` — PASS.
- `python qx_entry.py --api-selfcheck` — PASS.
- `tsc -p modern/tsconfig.json` — PASS (совместимая JavaScript-сборка).
- `python tests/run_browser_suite.py --only browser_tz_multi_ai.py --timeout 90` — Chromium PASS (3 ТЗ, выбор документов, AI-коррекция, сохранность цены, проект).
- Исходник Inno Setup содержит этап настройки AI после копирования QX и до запуска приложения, с отключением загрузки в тихом режиме.

## Не проверялось — ограничения окружения

- Установка официального Windows Ollama CLI из GitHub на живом Windows 10/11.
- Загрузка/инференс полноценной модели Qwen3 4B Instruct (~2,5 ГБ), использование GPU.
- Сборка и реальная установка Windows EXE, Inno Setup и Windows PowerShell 5.1.
- Windows PowerShell `auto_ai.ps1` проверен тестами исходного кода, но **не запускался** в Windows; это тестовый сценарий, а не сертифицированный Windows-инсталлятор.

Важное замечание: скрипт подлежит первому ручному тесту на Windows перед внедрением на рабочих компьютерах. Существующие данные QX и цены намеренно не удаляются.
