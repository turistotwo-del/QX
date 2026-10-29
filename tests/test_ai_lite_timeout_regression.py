"""Regression coverage for local AI Lite stalls and the CPU prompt budget."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, MagicMock
import asyncio
import json
import httpx
from modern import local_ai, tz_ai, lite_boot
from modern.server import app

ROOT = Path(__file__).resolve().parents[1]


class LiteTimeoutTests(TestCase):
    def test_tz_prompt_for_cpu_model_is_bounded_and_contains_quotes(self):
        text = ('Служебное описание, не относящееся к характеристикам. ' * 500 +
                '\nТИП 1. Оперативная память не менее 16 ГБ. Моноблок 23.8 дюйма.')
        req={'title':'ТИП 1', 'product_type':'aio24', 'ram_gb_min':8, 'quantity':1}
        prompt, truncated=tz_ai._lite_prompt(text, req)
        self.assertTrue(truncated)
        self.assertLess(len(prompt), 5300)
        self.assertIn('ram_gb_min',prompt)
        self.assertIn('Оперативная память не менее 16 ГБ',prompt)
        self.assertNotIn('custom_case_price',prompt)
        self.assertIn('"proposals"',prompt)
        # The quote validator still sees the *whole*, unchanged original text.
        verified = tz_ai.verify_ai_proposals({'proposals':[{'field':'ram_gb_min', 'value':16,
                  'quote':'Оперативная память не менее 16 ГБ'}]}, text, req)
        self.assertEqual(verified['proposals'][0]['value'],16)

    def test_keyboard_gets_keyboard_fields_and_not_200_items(self):
        prompt, _ = tz_ai._lite_prompt('Клавиатура проводная USB, не менее 104 клавиш.',
                                      {'product_type':'keyboard', 'title':'Клавиатура'})
        self.assertIn('keyboard_keys_min',prompt)
        self.assertNotIn('cpu_l3_mb_min',prompt)

    def test_lite_sends_smaller_json_budget(self):
        text='Оперативная память не менее 16 ГБ. Моноблок 23.8 дюйма.'
        reply=json.dumps({'proposals':[{'field':'ram_gb_min','value':16,
                                       'quote':'Оперативная память не менее 16 ГБ'}]},ensure_ascii=False)
        with patch.object(local_ai,'available_models',return_value={'models':[local_ai.LITE_MODEL]}), \
             patch.object(local_ai,'_lite_answer',return_value=reply) as inference:
            result=tz_ai.analyze_tz(text, {'title':'Моноблок','product_type':'aio24','ram_gb_min':8},local_ai.LITE_MODEL)
        self.assertEqual(result['proposals'][0]['value'],16)
        self.assertEqual(inference.call_args.kwargs['max_tokens'],280)
        self.assertLess(len(inference.call_args.args[0]),4500)

    def test_timeout_has_useful_message_and_finite_wait(self):
        with patch.object(local_ai,'_lite_available',return_value=True), \
             patch.object(local_ai,'urlopen',side_effect=TimeoutError('timed out')) as call:
            with self.assertRaisesRegex(RuntimeError,'модель не успела ответить'):
                local_ai._lite_answer('проверка',max_tokens=10,timeout=12)
        self.assertEqual(call.call_args.kwargs['timeout'],12)

    def test_diagnostic_uses_a_real_short_inference(self):
        with patch.object(local_ai,'_lite_available',return_value=True), \
             patch.object(local_ai,'_lite_answer',return_value='готов') as inference:
            result=local_ai.lite_diagnostic()
        self.assertTrue(result['ok'])
        self.assertEqual(inference.call_args.kwargs['max_tokens'],18)
        self.assertEqual(inference.call_args.kwargs['timeout'],35)

    def test_diagnostic_api_does_not_make_model_up(self):
        async def check():
            with patch.object(local_ai,'lite_diagnostic',return_value={'ok':False,'detail':'Модель недоступна'}):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
                    response=await client.get('/api/parse/ai/diagnostic')
                    self.assertEqual(response.status_code,200)
                    self.assertFalse(response.json()['ok'])
        asyncio.run(check())

    def test_windows_model_server_uses_smaller_context(self):
        source=(ROOT/'modern/lite_boot.py').read_text('utf-8')
        self.assertIn("'--ctx-size', '4096'",source)
        self.assertIn("'--threads', '6'",source)

    def test_ui_has_explicit_inference_test_and_nonblocking_progress(self):
        js=(ROOT/'modern/web/app.js').read_text('utf-8')
        self.assertIn('tz-ai-diagnostic',js)
        self.assertIn('parse/ai/diagnostic',js)
        self.assertIn('progressTimer',js)
        self.assertNotIn('await busy(task);',js)
