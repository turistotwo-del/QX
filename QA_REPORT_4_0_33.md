# QX 4.0.33 QA
- `python -m pytest -q tests/ modern/test_modern.py modern/test_337_regression.py modern/test_peripheral_choice.py`: 337 passed; 25 unittest subtests; 3 warnings.
- `PYTHONPATH=. python tests/browser_smoke.py`: OK.
- `PYTHONPATH=. python tests/browser_tz_multi_ai.py`: OK.
- `PYTHONPATH=.:tests python tests/browser_save_4033.py`: OK (native-bridge mock, downloadable fallback, cancellation).
- `tsc --project modern/tsconfig.json`: OK.
- Windows executable + PowerShell SaveFileDialog manual run: NOT TESTED (Windows unavailable).
