"""QX local AI must never freeze the full desktop Uvicorn event loop."""
from __future__ import annotations
import asyncio
import time
import unittest
from unittest.mock import patch
import httpx
from modern.server import app
from modern import tender_store as store
from modern import local_ai


class TestAINonblocking(unittest.TestCase):
    def test_health_responds_during_slow_local_inference(self):
        async def test():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url='http://testserver') as client:
                with patch.object(store,'detail',return_value={'documents':[{'id':'first'}]}), \
                     patch.object(store,'document_bytes',return_value=('contract.txt',b'Contract')):
                    def slow_answer(*args):
                        time.sleep(0.50)
                        return {'text':'OK'}
                    with patch.object(local_ai,'local_question',side_effect=slow_answer):
                        req=asyncio.create_task(client.post('/api/tenders/abc/local-ai',
                                                            json={'question':'BIOS?', 'model':'demo'}))
                        await asyncio.sleep(0.08)
                        start=time.monotonic()
                        ping=await asyncio.wait_for(client.get('/api/health'),timeout=.25)
                        elapsed=time.monotonic()-start
                        self.assertEqual(ping.status_code,200)
                        self.assertLess(elapsed,.25)
                        rsp=await req
                        self.assertEqual(rsp.status_code,200)
                        self.assertEqual(rsp.json()['answer']['text'],'OK')
        asyncio.run(test())


if __name__=='__main__':unittest.main()
