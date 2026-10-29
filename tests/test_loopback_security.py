"""Reject cross-site browser commands to localhost (no tender state mutation)."""
import unittest
from fastapi.testclient import TestClient
from modern.server import app
from modern.loopback_security import _same_origin

class TestLocalSecurity(unittest.TestCase):
    def setUp(self):self.client=TestClient(app)

    def test_same_origin_requests_work(self):
        r=self.client.get('/api/health',headers={'Origin':'http://testserver','Sec-Fetch-Site':'same-origin'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(r.json()['ok'])

    def test_cross_site_post_rejected_before_data_processing(self):
        r=self.client.post('/api/tenders',json={'title':'FORGED'},headers={'Origin':'https://evil.example','Sec-Fetch-Site':'cross-site'})
        self.assertEqual(r.status_code,403)

    def test_origin_null_rejected(self):
        r=self.client.get('/api/health',headers={'Origin':'null'})
        self.assertEqual(r.status_code,403)

    def test_cross_site_get_rejected(self):
        r=self.client.get('/api/tenders',headers={'Sec-Fetch-Site':'cross-site'})
        self.assertEqual(r.status_code,403)

    def test_bad_host_rejected(self):
        r=self.client.get('/api/health',headers={'Host':'attacker.example'})
        self.assertEqual(r.status_code,403)

    def test_other_local_port_not_same_origin(self):
        self.assertFalse(_same_origin('http://127.0.0.1:8765','127.0.0.1:8766'))
        self.assertTrue(_same_origin('http://127.0.0.1:8765','127.0.0.1:8765'))
        self.assertFalse(_same_origin('https://127.0.0.1:8765','127.0.0.1:8765'))

if __name__=='__main__':unittest.main()
