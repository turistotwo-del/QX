# QX 4.0.24 — итоги проверки 22.10.2026

- `python -m unittest discover -s tests -q`: **241/241 OK**.
- `python -m unittest modern.test_modern modern.test_peripheral_choice modern.test_337_regression -q`: **27/27 OK**.
- `python qx_entry.py --selfcheck`: OK.
- `python qx_entry.py --api-selfcheck`: OK, включая документ, БД и BIOS.
- `python windows_build/release_metadata.py --check`: OK.
- `tsc -p modern/tsconfig.json`: OK.
- Реальный браузерный Chromium smoke: **OK** (расчёт, ТЗ, тендер, сроки, комментарии).
- Отдельные браузерные сценарии локального поиска, выбора GGUF и импорта данных 3.3.7: **OK**.
- Выгрузка Word-отчёта: новые тесты включены в набор Python. Пример отчёта отрендерен в Word-совместимый PDF и визуально проверен.

**Непроверенное / неготовое:** первое сетевое развёртывание переносного Python и запуск на Windows; работа реальной GGUF-модели на Windows; массовая интеграция ЕИС по номеру через СОИ. Эти функции не подтверждаются результатами Linux-тестов.
