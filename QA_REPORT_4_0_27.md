# Проверки QX Подборщик 4.0.27 Lite — 22.10.2026

- `python -m unittest discover -s tests -p test_*.py -q`: **258/258**, OK.
- `python -m unittest -q modern.test_modern modern.test_337_regression modern.test_peripheral_choice`: **27/27**, OK.
- `python qx_entry.py --selfcheck`: OK.
- `tsc -p modern/tsconfig.json`: OK (обновлён app.js).
- Chromium `browser_tz_multi_ai.py`: OK (включая несколько ТЗ и предложения AI).
- Chromium `browser_smoke.py`: OK.
- Chromium `browser_ai_offline.py`: OK.
- Модель Qwen2.5, движок llama.cpp, SHA256 из официального GitHub API не загружались во время тестов. Запуск на Windows не проверен; сборка DEV/portable.
- `self_test.py` от устаревшей Streamlit-версии в исходном архиве не запускается: отсутствует `desktop_launcher.py`. Скрипт сборки Windows исправлен: для QX Modern выполняется `qx_entry.py --selfcheck`.
- Движок AI устанавливается через `portable/auto_ai.ps1`; файл модели загружается по HTTPS с Hugging Face, проверяется GGUF-магия и размер. SHA-256 модели по-прежнему не фиксируется.
