"""Simulated Windows mutex behavior; true Windows OS API requires Windows CI."""
import unittest
from unittest.mock import MagicMock, patch
import qx_entry
from modern import windows_instance


class InstanceTests(unittest.TestCase):
    def test_nonwindows_is_noop(self):
        with patch.object(windows_instance.sys,'platform','linux'):
            with windows_instance.desktop_instance() as first:
                self.assertTrue(first)

    def test_first_instance_holds_mutex_through_window_lifetime(self):
        kernel,handle=object(),object()
        events=[]
        with patch.object(windows_instance.sys,'platform','win32'), \
             patch.object(windows_instance,'_create_windows_mutex',return_value=(kernel,handle,False)), \
             patch.object(windows_instance,'_close_windows_mutex',side_effect=lambda *a:events.append('closed')) as close:
            with windows_instance.desktop_instance() as first:
                self.assertTrue(first)
                self.assertEqual(events,[])
            self.assertEqual(events,['closed'])
            close.assert_called_once_with(kernel,handle)

    def test_duplicate_window_is_rejected_but_mutex_handle_closed(self):
        with patch.object(windows_instance.sys,'platform','win32'), \
             patch.object(windows_instance,'_create_windows_mutex',return_value=(1,2,True)), \
             patch.object(windows_instance,'_close_windows_mutex') as close:
            with windows_instance.desktop_instance() as first:
                self.assertFalse(first)
            close.assert_called_once_with(1,2)

    def test_run_desktop_does_not_spawn_duplicate_server(self):
        from contextlib import contextmanager
        @contextmanager
        def duplicate():yield False
        with patch.object(windows_instance,'desktop_instance',side_effect=duplicate), \
             patch.object(windows_instance,'already_running_message') as msg, \
             patch('modern.start.launch') as launch:
            self.assertEqual(qx_entry.run_desktop(),0)
        msg.assert_called_once()
        launch.assert_not_called()


if __name__=='__main__':unittest.main()
