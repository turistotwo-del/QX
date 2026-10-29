"""Offline-only checks for QX AI integration; never downloads a vendor executable/model."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import unittest

from modern import ollama_boot

ROOT = Path(__file__).resolve().parents[1]


class TestAutomaticAIInstallation(unittest.TestCase):
    def test_official_engine_is_pinned_and_verified_before_launch(self):
        script = (ROOT / 'portable' / 'auto_ai.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('https://github.com/ggml-org/llama.cpp/releases/download/b11815/', script)
        self.assertIn('asset.digest', script)
        self.assertLess(script.index('Get-FileHash'), script.index('Expand-Archive'))
        self.assertIn('qwen2.5-1.5b-instruct-q4_k_m.gguf', script)
        self.assertIn('Download-Model', script)
        self.assertIn('Check-Model', script)
        self.assertIn('lite-engine', script)
        self.assertIn('exit 0', script)  # Failed AI installation cannot kill QX startup.

    def test_portable_launcher_installs_once_and_preserves_app_data(self):
        script=(ROOT/'portable'/'start_qx.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('qx-lite-1.5b.ready', script)
        self.assertIn("'auto_ai.ps1'", script)
        self.assertIn('QX_DISABLE_AUTO_AI', script)
        self.assertIn("$env:QX_DATA_DIR = Join-Path $env:LOCALAPPDATA 'QXPodborshchik'",script)

    def test_native_installer_provisions_ai_before_first_run(self):
        script=(ROOT/'windows_build'/'QX_Setup.iss').read_text(encoding='utf-8')
        self.assertIn('Source: "..\\portable\\auto_ai.ps1"', script)
        self.assertIn('skipifsilent', script)  # No multi-GB download in unattended CI.
        self.assertLess(script.index('Description: "Установить локальную нейросеть QX AI"'),script.index('Description: "Запустить QX Подборщик"'))

    def test_existing_ollama_never_spawned_or_stopped_by_qx(self):
        with patch.object(ollama_boot.sys, 'platform', 'win32'), patch.object(ollama_boot, 'ollama_reachable', return_value=True), \
             patch.object(ollama_boot.subprocess, 'Popen') as popen:
            proc = ollama_boot.start_ollama()
            self.assertIsNone(proc)
            popen.assert_not_called()

    def test_qx_owned_process_stops_on_shutdown(self):
        proc=MagicMock()
        proc.poll.return_value=None
        ollama_boot.stop_ollama(proc)
        proc.terminate.assert_called_once_with()
        proc.wait.assert_called_once_with(timeout=5)

    def test_no_ai_download_during_app_start(self):
        with patch.object(ollama_boot.sys, 'platform', 'win32'), patch.object(ollama_boot, 'ollama_reachable', return_value=False), \
             patch.object(ollama_boot, 'runtime_candidates', return_value=()), \
             patch.object(ollama_boot.subprocess,'Popen') as popen:
            self.assertIsNone(ollama_boot.start_ollama())
            popen.assert_not_called()

    def test_qx_ai_model_auto_selected_in_ui(self):
        src = (ROOT/'modern'/'web'/'app.ts').read_text(encoding='utf-8')
        self.assertIn("installedModels.includes('qx-lite:1.5b')",src)
        self.assertIn("state.tzAiModel='qx-lite:1.5b'",src)
        self.assertIn('Применить отмеченные и пересчитать', src)


if __name__ == '__main__': unittest.main()
