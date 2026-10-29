# QX Подборщик 4.0.29 — исправление запуска GUI на Windows

## Причины зафиксированного пользователем падения
1. PowerShell 5.1 при передаче командной строки `python -c` удалял кавычки вокруг строки `"webview"`, что приводило к `NameError`.
2. Параметр `pip --only-binary=:all:` запрещал установку `proxy-tools`, потому что пакет в PyPI доступен только как исходный архив `.tar.gz`.

## Изменения
- Новый `portable/desktop_probe.py`, запускаемый файлом, а не через `-c`.
- Оконные зависимости устанавливаются через `pip --prefer-binary` (SDist допускается, преимущественно wheels).
- Повторная проверка реального импорта `webview` и `clr`, независимо от предыдущего маркера.
- Не удаляются `.qx_runtime`, `QX_AI`, рабочие проекты и SQLite базы.
- Сохранены отдельное окно WebView2, оригинальная QX-иконка и ярлыки из QX 4.0.28.
- Обновлён идентификатор версии QX 4.0.29, а также рецепт Inno Setup.

## Проверено в Linux
- `python -m unittest discover -s tests -p test_*.py -q`: 274/274.
- `python -m unittest -q modern.test_modern modern.test_337_regression modern.test_peripheral_choice`: 27/27.
- `python qx_entry.py --selfcheck`: OK.
- `python tests/browser_smoke.py`: Browser E2E OK.
- Содержимое ZIP и контроль целостности: ОК.

## Не проверено
- Реальная установка `pywebview` в Windows embedded Python, загрузка пакетов через сеть, фактический Win32 значок на панели задач. Это тестовый Windows Portable-патч, не подтверждённый испытанием на Windows.
