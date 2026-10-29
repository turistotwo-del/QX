"""Verify Windows --windowed launch failures are reported outside the EXE folder."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import qx_entry
from modern import tender_store


class TestStartupDiagnostics(unittest.TestCase):
    def test_gui_launch_failure_is_reported_and_logged_in_user_data(self):
        with tempfile.TemporaryDirectory(prefix='qx_gui_fail_') as tmp:
            app_dir=Path(tmp)/'user'
            with patch.object(tender_store, 'APP_DATA', app_dir), \
                 patch('modern.start.launch', side_effect=RuntimeError('WebView2 failed')):
                result=qx_entry.run_desktop()
            self.assertEqual(result,1)
            log=app_dir/'logs'/'QX_Startup_Error.log'
            self.assertTrue(log.is_file())
            self.assertIn('WebView2 failed',log.read_text(encoding='utf-8'))
            self.assertNotIn(str(Path(qx_entry.__file__).parent/'QX_Startup_Error.log'),str(log))

    def test_logging_failure_does_not_hide_original_problem(self):
        with tempfile.TemporaryDirectory(prefix='qx_gui_fail_') as tmp:
            obstacle=Path(tmp)/'not_a_directory'
            obstacle.write_text('DO NOT TOUCH',encoding='utf-8')
            with patch.object(tender_store, 'APP_DATA', obstacle), \
                 patch('modern.start.launch', side_effect=RuntimeError('failure')):
                result=qx_entry.run_desktop()
            self.assertEqual(result,1)
            self.assertEqual(obstacle.read_text(encoding='utf-8'),'DO NOT TOUCH')

    def test_normal_desktop_start_returns_success(self):
        with patch('modern.start.launch') as launch:
            self.assertEqual(qx_entry.run_desktop(),0)
        launch.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
