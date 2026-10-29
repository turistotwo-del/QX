import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
import asyncio
from modern import local_ai
from modern import tender_store
from modern.server import app


class OfflineSearchTests(unittest.TestCase):
    def test_offline_search_returns_true_excerpts_without_network(self):
        payload = ('Титульный лист\n'*300 +
                   'Гарантийный срок товара не менее 36 месяцев.\n' +
                   'Перечень оборудования').encode('utf-8')
        with patch.object(local_ai,'urlopen',side_effect=AssertionError('Network forbidden')), \
             patch.object(local_ai,'_gguf_answer',side_effect=AssertionError('No model')):
            info=local_ai.local_question([('Договор.txt',payload)], 'Какой гарантийный срок?', 'offline-search')
        self.assertEqual(info['model'],'offline-search')
        self.assertIn('36 месяцев',info['text'])
        self.assertIn('[Договор.txt; строка',info['text'])
        self.assertIn('без нейросети',info['mode'])

    def test_offline_search_does_not_invent_missing_terms(self):
        with patch.object(local_ai,'urlopen',side_effect=AssertionError('Network forbidden')):
            info=local_ai.local_question([('ТЗ.txt',b'keyboard monitor')], 'Реестровый BIOS?', 'offline-search')
        self.assertIn('не найден',info['text'])

    def test_source_warning_when_ai_cites_other_document(self):
        class FakeReply:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,size=-1):return json.dumps({'response':'Требуется [Несуществующий.txt; строка 999]'}).encode('utf-8')
        with patch.object(local_ai,'urlopen',return_value=FakeReply()):
            info=local_ai.local_question([('ТЗ.txt','Реестровый BIOS требуется.'.encode())],
                                         'Нужен ли BIOS?', 'qwen2.5:3b')
        self.assertIn('которых нет',info['warning'])
        self.assertIn('ТЗ.txt',info['sources'][0]['file'])

    def test_http_default_stays_offline(self):
        async def verify():
            with patch.object(tender_store,'detail',return_value={'documents':[{'id':'doc'}]}), \
                 patch.object(tender_store,'document_bytes',return_value=('ТЗ.txt','Реестровый BIOS требуется.'.encode())), \
                 patch.object(local_ai,'urlopen',side_effect=AssertionError('Network forbidden')):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
                    r=await client.post('/api/tenders/abc/local-ai',json={'question':'Нужен ли реестровый BIOS?'})
                self.assertEqual(r.status_code,200,r.text)
                self.assertEqual(r.json()['answer']['model'],'offline-search')
        asyncio.run(verify())


if __name__=='__main__': unittest.main()
