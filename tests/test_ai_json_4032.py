"""AI Lite JSON truncation / UI regression tests, all offline."""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from modern import local_ai, tz_ai

ROOT = Path(__file__).resolve().parents[1]


class LocalJsonRegression(unittest.TestCase):
    def setUp(self):
        self.text = 'Оперативная память не менее 16 ГБ. Накопитель SSD не менее 512 ГБ.'
        self.req = {'title': 'Моноблок', 'product_type': 'aio24', 'ram_gb_min': 0}
        self.one = {'field': 'ram_gb_min', 'value': 16,
                    'quote': 'Оперативная память не менее 16 ГБ'}

    def test_truncated_preserves_only_closed_proposal(self):
        output = '{"proposals":[' + json.dumps(self.one, ensure_ascii=False) + ',{"field":"ssd_gb_min","value":5'
        obj, partial = tz_ai._read_model_json(output)
        self.assertTrue(partial)
        self.assertEqual(obj, {'proposals': [self.one]})

    def test_json_with_braces_in_citation(self):
        obj = {'proposals': [dict(self.one, quote='Оперативная память {ОЗУ} 16 ГБ')]}
        raw, incomplete = tz_ai._read_model_json('```json\n' + json.dumps(obj, ensure_ascii=False) + '\n```')
        self.assertEqual(obj, raw)
        self.assertFalse(incomplete)

    def test_incomplete_quote_never_rescued(self):
        s = '{"proposals":[{"field":"ram_gb_min","value":16,"quote":"Оперативная память'
        raw, incomplete = tz_ai._read_model_json(s)
        self.assertTrue(incomplete)
        self.assertEqual(raw['proposals'], [])

    def test_salvaged_proposal_passes_quote_validation(self):
        s = '{"proposals":[' + json.dumps(self.one, ensure_ascii=False) + ',{"field":"ssd_gb_min"'
        with patch.object(local_ai, 'available_models', return_value={'models':[local_ai.LITE_MODEL]}), \
                patch.object(local_ai,'_lite_answer', return_value=s) as infer:
            result = tz_ai.analyze_tz(self.text, self.req, local_ai.LITE_MODEL)
        self.assertEqual(len(result['proposals']), 1)
        self.assertEqual(result['proposals'][0]['value'], 16)
        self.assertIn('оборвала JSON', result['warning'])
        self.assertEqual(infer.call_count, 1)

    def test_retry_tiny_and_does_not_invent(self):
        s = '{"proposals":[{"field":"ram_gb_min","value":16,"quote":"обрыв'
        with patch.object(local_ai, 'available_models', return_value={'models':[local_ai.LITE_MODEL]}), \
                patch.object(local_ai, '_lite_answer', side_effect=[s, '{"proposals":[]}']) as infer:
            result = tz_ai.analyze_tz(self.text, self.req, local_ai.LITE_MODEL)
        self.assertEqual(result['proposals'], [])
        self.assertEqual(infer.call_count, 2)
        self.assertLess(len(infer.call_args.args[0]), 2300)
        self.assertEqual(infer.call_args.kwargs['max_tokens'], 210)
        self.assertTrue(infer.call_args.kwargs['json_mode'])

    def test_retry_failed_is_safe_empty_response(self):
        with patch.object(local_ai,'available_models',return_value={'models':[local_ai.LITE_MODEL]}), \
             patch.object(local_ai,'_lite_answer',side_effect=['{bad',RuntimeError('модель занята')]):
            result=tz_ai.analyze_tz(self.text,self.req,local_ai.LITE_MODEL)
        self.assertEqual(result['proposals'], [])
        self.assertIn('оборвала JSON', result['warning'])

    def test_wrong_position_quote_not_inserted_even_on_salvage(self):
        position={'title':'Позиция 1','product_type':'aio24','raw_text':'Позиция 1 SSD 256 ГБ'}
        text='Позиция 1 SSD 256 ГБ\nПозиция 2 SSD 512 ГБ'
        raw='{ "proposals": [' + json.dumps({'field':'ssd_gb_min','value':512,'quote':'Позиция 2 SSD 512 ГБ'},ensure_ascii=False) + ', {"field":"'
        with patch.object(local_ai,'available_models',return_value={'models':[local_ai.LITE_MODEL]}), \
             patch.object(local_ai,'_lite_answer',return_value=raw):
            result=tz_ai.analyze_tz(text,position,local_ai.LITE_MODEL)
        self.assertEqual(result['proposals'], [])

    def test_json_request_uses_supported_format(self):
        data=json.dumps({'choices':[{'message':{'content':'{"proposals":[]}'}}]}).encode()
        response=MagicMock()
        response.__enter__.return_value=response
        response.read.return_value=data
        with patch.object(local_ai,'_lite_available',return_value=True), \
             patch.object(local_ai,'urlopen',return_value=response) as call:
            self.assertIn('proposals',local_ai._lite_answer('проверь',json_mode=True))
        sent=json.loads(call.call_args.args[0].data.decode())
        self.assertEqual(sent['response_format']['type'],'json_object')

    def test_unsupported_json_mode_fallback(self):
        err=HTTPError(local_ai.LITE_API_URL,400,'not supported',hdrs=None,fp=None)
        data=json.dumps({'choices':[{'message':{'content':'{"proposals":[]}'}}]}).encode()
        response=MagicMock()
        response.__enter__.return_value=response
        response.read.return_value=data
        with patch.object(local_ai,'_lite_available',return_value=True), \
             patch.object(local_ai,'urlopen',side_effect=[err,response]) as call:
            self.assertIn('proposals',local_ai._lite_answer('проверь',json_mode=True))
        self.assertEqual(call.call_count,2)
        self.assertNotIn('response_format',json.loads(call.call_args.args[0].data.decode()))

    def test_checkbox_dimension_override(self):
        css=(ROOT/'modern/web/style.css').read_text('utf-8')
        ts=(ROOT/'modern/web/app.ts').read_text('utf-8')
        js=(ROOT/'modern/web/app.js').read_text('utf-8')
        self.assertIn('min-height:16px',css)
        self.assertIn('class="tz-ai-toggle"',ts)
        self.assertIn('class="tz-ai-toggle"',js)

if __name__ == '__main__': unittest.main()
