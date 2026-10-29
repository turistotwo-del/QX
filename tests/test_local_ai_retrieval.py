import io
import json
import unittest
from unittest.mock import patch
from modern import local_ai

class FakeReply:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,size=-1):return json.dumps({'response':'Требование найдено [ТЗ.txt; строка 390]'}).encode()

class TestRetrieval(unittest.TestCase):
    def test_relevant_tail_in_prompt(self):
        text='\n'.join(f'Строка {i}: посторонние характеристики предмета закупки' for i in range(390)) + '\nРеестровый BIOS обязателен; прошивка должна быть в реестре ПО.'
        doc=[('ТЗ.txt',text.encode('utf-8'))]
        payload=[]
        def capture(request,timeout):
            self.assertEqual(request.full_url, 'http://127.0.0.1:11434/api/generate')
            payload.append(json.loads(request.data))
            return FakeReply()
        with patch.object(local_ai,'urlopen',capture):
            r=local_ai.local_question(doc,'Требуется ли реестровый BIOS?')
        self.assertIn('Реестровый BIOS обязателен',payload[0]['prompt'])
        self.assertIn('строка 391',payload[0]['prompt'])
        self.assertLess(len(payload[0]['prompt']),18000)
        self.assertEqual(len(r['sources'])>0,True)
    def test_no_matching_evidence_not_hallucinated(self):
        with patch.object(local_ai,'urlopen',side_effect=AssertionError('No call permitted')):
            r=local_ai.local_question([('ТЗ.txt',b'Apple banana coconut')], 'Сколько дней на оплату?')
        self.assertIn('не найдено',r['text'])
    def test_unique_bios_clause_survives_many_similar_clauses(self):
        # Regression: sampling before relevance ranking could drop one unique
        # clause in the middle of thousands of equally ranked BIOS mentions.
        bulk = ['BIOS поддерживает загрузку операционной системы.'] * 8200
        bulk[4157] = 'BIOS БЕШТАУ должен иметь отдельную реестровую запись в российском реестре ПО.'
        text = '\n'.join(bulk)
        captured=[]
        def fetch(request, timeout):
            captured.append(json.loads(request.data)['prompt'])
            return FakeReply()
        with patch.object(local_ai, 'urlopen', fetch):
            result=local_ai.local_question([('ТЗ.txt', text.encode())], 'Обязателен ли реестровый BIOS БЕШТАУ?')
        self.assertIn('BIOS БЕШТАУ должен иметь',captured[0])
        self.assertIn('строка 4158',captured[0])
        self.assertLess(len(captured[0]),18000)
        self.assertEqual(result['mode'],'Настоящая локальная модель Ollama')

    def test_incomplete_scanned_pdf_does_not_produce_false_no_requirement(self):
        class BlankPage:
            def extract_text(self): return ''
        class Reader:
            def __init__(self, stream): self.pages=[BlankPage()]
        with patch('pypdf.PdfReader', Reader), patch.object(local_ai,'urlopen',side_effect=AssertionError('No model call')):
            result=local_ai.local_question([('Контракт.pdf',b'%PDF mocked'),('Приложение.txt','Условия проекта'.encode())], 'Обязателен ли BIOS?')
        self.assertEqual(len(result['incomplete_files']),1)
        self.assertIn('неполный',result['warning'].lower())
        self.assertNotIn('BIOS не требуется',result['text'])

    def test_incomplete_flag_passed_to_real_model(self):
        captured=[]
        def fetch(request,timeout):
            captured.append(json.loads(request.data)['prompt'])
            return FakeReply()
        with patch.object(local_ai,'urlopen',fetch):
            result=local_ai.local_question([('Не читается.xyz',b''),('ТЗ.txt','Реестровый BIOS обязателен.'.encode())], 'Есть ли требование к реестровому BIOS?')
        self.assertIn('НЕ УТВЕРЖДАЙ',captured[0])
        self.assertEqual(len(result['incomplete_files']),1)
        self.assertIn('неполный',result['warning'].lower())

    def test_local_models_status_is_real_and_read_only(self):
        class TagReply:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,amount):return b'{"models":[{"name":"qwen2.5:3b"},{"name":"not valid model name"}]}'
        def fetch(request,timeout):
            self.assertEqual(request.full_url,local_ai.OLLAMA_TAGS_URL)
            self.assertIsNone(request.data)
            return TagReply()
        with patch.object(local_ai,'urlopen',fetch):
            status=local_ai.available_models()
        self.assertEqual(status['models'],['qwen2.5:3b'])
        with patch.object(local_ai,'urlopen',side_effect=OSError('offline')):
            status=local_ai.available_models()
        self.assertFalse(status['available'])
        self.assertFalse(status['models'])

    def test_empty_document(self):
        with self.assertRaises(ValueError):local_ai.local_question([], 'BIOS?')

if __name__=='__main__':unittest.main()
