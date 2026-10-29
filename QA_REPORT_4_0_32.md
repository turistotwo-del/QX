# QX 4.0.32 — QA

- 328 pytest тестов успешно, 20 под-тестов, 2 сторонних deprecation warning.
- tsc --noEmit — успешно.
- tests/browser_smoke.py — Browser E2E: OK (Chromium Linux).
- tests/browser_tz_ai_autofill.py — Browser TZ AI safe auto-fill: OK (Chromium Linux, mock model).
- tests/browser_tz_multi_ai.py — Browser multi TZ + AI review: OK (Chromium Linux, mock model).
- Дополнительно тестируются: обрезанный JSON; закрытый объект и оборванный второй; незакрытая цитата; одна попытка повторения; ошибка повторной попытки; защита от смешения позиций; переключение со structured response; CSS.
- Реальная GGUF-модель на Windows не запускалась, точные тайминги на CPU неизвестны.
- Legacy self_test.py был падающим до исправления (проверено на исходной 4.0.31): assert DDR4; этот баг не исправлялся и не считается пройденным.
