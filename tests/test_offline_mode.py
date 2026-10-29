"""Explicit air-gapped deployment mode and deterministic browser tests."""
import unittest
from unittest.mock import patch
from modern.server import rate


class TestOfflineMode(unittest.TestCase):
    def test_currency_uses_cached_value_without_network(self):
        with patch.dict('os.environ',{'QX_OFFLINE_MODE':'1'}), \
             patch('modern.server.get_usd_rate',side_effect=AssertionError('Attempted external HTTP')), \
             patch('modern.server.storage.load_settings',return_value={'usd_rate_cached':99.11,'usd_rate_date_cached':'21.10.2026'}):
            result=rate()
        self.assertEqual(result['rate'],99.11)
        self.assertEqual(result['date'],'21.10.2026')
        self.assertFalse(result['live'])
        self.assertIn('Офлайн',result['error'])

    def test_persisted_offline_setting_disables_network(self):
        with patch.dict('os.environ',{'QX_OFFLINE_MODE':'0'}), \
             patch('modern.server.get_usd_rate',side_effect=AssertionError('Attempted external HTTP')), \
             patch('modern.server.storage.load_settings',return_value={'offline_mode':True,'usd_rate_cached':78.5}):
            result=rate()
        self.assertFalse(result['live'])
        self.assertEqual(result['rate'],78.5)

    def test_online_mode_keeps_existing_rate_refresh(self):
        from core.currency import RateInfo
        expected=RateInfo(90.,'22.10.2026',True)
        with patch.dict('os.environ',{'QX_OFFLINE_MODE':'0'}), \
             patch('modern.server.get_usd_rate',return_value=expected) as fetch, \
             patch('modern.server.storage.save_settings') as save, \
             patch('modern.server.storage.load_settings',return_value={'usd_rate_cached':80.,'usd_rate_date_cached':''}):
            result=rate()
        fetch.assert_called_once()
        save.assert_called_once()
        self.assertTrue(result['live'])
        self.assertEqual(result['rate'],90.)


if __name__=='__main__':unittest.main()
