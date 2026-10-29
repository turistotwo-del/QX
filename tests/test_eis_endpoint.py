"""No network; EIS route never modifies a tender or infers a contract status."""
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from modern.server import app

N='0322100002526000466'

class TestEisRoute(unittest.TestCase):
    def setUp(self):self.client=TestClient(app)
    def test_valid_number_lookup_only(self):
        with patch('modern.server.tenders.get',return_value={'id':'test','number':N,'status':'Черновик'}), \
             patch('modern.eis_public.lookup_notice',return_value={'available':False,'matches':[],'search_url':'https://zakupki.gov.ru/'}):
            response=self.client.post('/api/tenders/test/eis/lookup')
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json()['available'])
    def test_draft_requires_notice(self):
        with patch('modern.server.tenders.get',return_value={'id':'test','number':''}):
            response=self.client.post('/api/tenders/test/eis/lookup')
            self.assertEqual(response.status_code,422)
    def test_missing_tender(self):
        with patch('modern.server.tenders.get',return_value=None):
            response=self.client.post('/api/tenders/missing/eis/lookup')
            self.assertEqual(response.status_code,404)

if __name__=='__main__':unittest.main()
