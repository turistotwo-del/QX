# QX 4.0.28 — native desktop start hotfix

- Исправлена причина ERR_CONNECTION_REFUSED из-за старого Edge portable fallback: внешний `msedge.exe --app` больше не запускается; сервер живёт до закрытия собственного окна QX.
- При первом запуске устанавливаются pywebview и pythonnet в уже существующий private Python без повторной загрузки QX AI и основных зависимостей.
- Восстановлено создание ярлыка на реальном рабочем столе и в меню Пуск, с `assets/qx_icon.ico` и действующим `ЗАПУСТИТЬ_QX.cmd`.
- Приложение задаёт стабильный Windows AppUserModelID; иконка устанавливается на Win32 окно и кнопку панели задач через `WM_SETICON`.
- `python -m unittest discover -s tests -p test_*.py -q`: 270/270 во втором полном прогоне, 1 нестабильный тест тайм-аута при первом запуске набора.
- `python -m unittest -q modern.test_modern modern.test_337_regression modern.test_peripheral_choice`: 27/27.
- `python qx_entry.py --selfcheck`: OK.
- `PYTHONPATH=. python tests/browser_smoke.py`: Browser E2E OK.
- **Запуск на реальной Windows, установка pywebview и фактическая иконка панели задач НЕ проверены**. Это тестовая portable-сборка, а не проверенный Windows EXE/установщик.
