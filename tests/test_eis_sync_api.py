"""HTTP contract for single-action EIS import; no remote requests."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from modern.server import app

NUMBER = '0322100002526000466'


class EisSyncAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_defaults_and_exact_number_are_forwarded(self):
        expected = {'tender': {'id': 't1', 'number': NUMBER}, 'partial': False}
        with patch('modern.eis_sync.sync_notice', return_value=expected) as sync:
            response = self.client.post('/api/eis/import', json={'number': NUMBER})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        sync.assert_called_once_with(NUMBER, download_documents=True, tender_id='')

    def test_metadata_only_selected_card(self):
        with patch('modern.eis_sync.sync_notice', return_value={}) as sync:
            response = self.client.post('/api/eis/import', json={
                'number': NUMBER, 'download_documents': False, 'tender_id': 't1'})
        self.assertEqual(response.status_code, 200)
        sync.assert_called_once_with(NUMBER, download_documents=False, tender_id='t1')

    def test_types_and_unknown_fields_rejected_before_work(self):
        invalid = [None, [], {}, {'number': 322100002526000466},
                   {'number': NUMBER, 'download_documents': 'false'},
                   {'number': NUMBER, 'download_documents': 1},
                   {'number': NUMBER, 'tender_id': 1},
                   {'number': NUMBER, 'url': 'http://127.0.0.1/'},
                   {'number': '1' * 1000}]
        with patch('modern.eis_sync.sync_notice') as sync:
            for body in invalid:
                with self.subTest(body=body):
                    self.assertEqual(self.client.post('/api/eis/import', json=body).status_code, 422)
            sync.assert_not_called()

    def test_lookup_errors_have_actionable_http_status(self):
        for error, status in [(ValueError('Неверный номер'), 422), (KeyError('Закупка не найдена'), 404)]:
            with self.subTest(status=status), patch('modern.eis_sync.sync_notice', side_effect=error):
                response = self.client.post('/api/eis/import', json={'number': NUMBER})
                self.assertEqual(response.status_code, status)
                self.assertIn(str(error).strip("'"), response.json()['detail'])

    def test_cross_site_cannot_trigger_download(self):
        with patch('modern.eis_sync.sync_notice') as sync:
            response = self.client.post('/api/eis/import', json={'number': NUMBER},
                                        headers={'Origin': 'https://example.org'})
            self.assertEqual(response.status_code, 403)
            sync.assert_not_called()


if __name__ == '__main__':
    unittest.main()
