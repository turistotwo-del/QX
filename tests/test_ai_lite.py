"""Offline regression checks for compact AI installer/server integration."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, MagicMock
import io
import json

from modern import local_ai, lite_boot

ROOT=Path(__file__).resolve().parents[1]

class TestAILite(TestCase):
    def test_installer_uses_compact_engine_and_model(self):
        script=(ROOT/'portable'/'auto_ai.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('llama-b11815-bin-win-cpu-x64.zip',script)
        self.assertIn('qwen2.5-1.5b-instruct-q4_k_m.gguf',script)
        self.assertIn('Get-FileHash',script)
        self.assertIn('asset.digest',script)
        self.assertNotIn('ollama-windows-amd64.zip',script)
        self.assertNotIn('qwen3:4b-instruct',script)
        self.assertIn('qx-lite-1.5b.ready',script)
        self.assertIn('exit 0',script)

    def test_default_model_is_lite(self):
        ts=(ROOT/'modern'/'web'/'app.ts').read_text(encoding='utf-8')
        js=(ROOT/'modern'/'web'/'app.js').read_text(encoding='utf-8')
        self.assertIn("state.tzAiModel='qx-lite:1.5b'",ts)
        self.assertIn("state.tzAiModel = 'qx-lite:1.5b'",js)

    def test_local_inference_not_remote(self):
        self.assertEqual(local_ai.LITE_API_URL,'http://127.0.0.1:11435/v1/chat/completions')
        output=json.dumps({'choices':[{'message':{'content':'[a.docx; Раздел 2] Цена 10 рублей'}}]}).encode()
        response=MagicMock()
        response.__enter__.return_value=response
        response.read.return_value=output
        with patch.object(local_ai,'_lite_available', return_value=True), \
             patch.object(local_ai,'urlopen',return_value=response) as request:
            self.assertIn('Цена 10', local_ai._lite_answer('Сумма?'))
            sent=json.loads(request.call_args[0][0].data.decode())
            self.assertEqual(sent['max_tokens'],500)
            self.assertFalse(sent['stream'])
            self.assertEqual(sent['temperature'],0.0)

    def test_no_lite_process_if_not_installed(self):
        with patch.object(lite_boot.sys,'platform','win32'), \
             patch.object(lite_boot,'lite_reachable',return_value=False), \
             patch.object(lite_boot,'ENGINE',Path('/definitely-not-installed-qx-lite.exe')), \
             patch.object(lite_boot.subprocess,'Popen') as popen:
            self.assertIsNone(lite_boot.start_lite())
            popen.assert_not_called()

    def test_tz_rejects_unsupported_numeric_suggestion(self):
        from modern.tz_ai import verify_ai_proposals
        result=verify_ai_proposals({'proposals':[{'field':'ram_gb_min','value':64,'quote':'Оперативная память не менее 16 ГБ'}]},'Оперативная память не менее 16 ГБ',{'ram_gb_min':8})
        self.assertFalse(result['proposals'])
