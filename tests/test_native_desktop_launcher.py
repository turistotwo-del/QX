"""QX 4.0.28 native desktop regression tests, no Windows side effects."""
import sys
import types
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, Mock

from modern import start


class DesktopLaunchTests(TestCase):
    def test_pywebview_creates_qx_window_with_native_title_and_no_external_edge(self):
        registered = []
        class ShownEvent:
            def __iadd__(self, callback):
                registered.append(callback)
                return self
        class FakeWindow:
            def __init__(self):
                self.events = types.SimpleNamespace(shown=ShownEvent())
        fake_view = types.ModuleType('webview')
        fake_view.create_window = Mock(return_value=FakeWindow())
        fake_view.start = Mock()
        with patch.dict(sys.modules, {'webview': fake_view}), \
             patch.object(start, 'ROOT', Path(__file__).resolve().parents[1]):
            start._show_windows_qx('http://127.0.0.1:54321/')
        fake_view.create_window.assert_called_once()
        self.assertEqual(fake_view.create_window.call_args.args[0], 'QX Подборщик — Modern')
        self.assertEqual(fake_view.create_window.call_args.args[1], 'http://127.0.0.1:54321/')
        self.assertTrue(registered)
        self.assertEqual(fake_view.start.call_args.kwargs['gui'], 'edgechromium')
        self.assertEqual(fake_view.start.call_args.kwargs['debug'], False)

    def test_missing_pywebview_does_not_spawn_browser_with_dead_url(self):
        with patch.dict(sys.modules, {'webview': None}):
            with self.assertRaisesRegex(RuntimeError, 'pywebview'):
                start._show_windows_qx('http://127.0.0.1:54321/')

    def test_webview_runtime_exception_surfaces_explicit_diagnostic(self):
        fake_view = types.ModuleType('webview')
        fake_view.create_window = Mock(return_value=types.SimpleNamespace(
            events=types.SimpleNamespace(shown=type('E', (), {'__iadd__': lambda a,b: a})())))
        fake_view.start = Mock(side_effect=OSError('Missing WebView2 Runtime'))
        with patch.dict(sys.modules, {'webview': fake_view}):
            with self.assertRaisesRegex(RuntimeError, 'WebView2'):
                start._show_windows_qx('http://127.0.0.1:54321/')

    def test_portable_upgrade_reinstalls_only_native_window(self):
        root = Path(__file__).resolve().parents[1]
        boot = (root/'portable/start_qx.ps1').read_text('utf-8-sig')
        shortcut = (root/'modern/create_shortcut_modern.ps1').read_text('utf-8-sig')
        requirements = (root/'portable/requirements_desktop.txt').read_text('utf-8')
        self.assertIn('desktop-webview2-4.0.29.marker', boot)
        self.assertIn('requirements_desktop.txt', boot)
        self.assertIn('ready-4.0.25.marker', boot)
        self.assertIn('pywebview==6.2.1', requirements)
        self.assertIn('ЗАПУСТИТЬ_QX.cmd', shortcut)
        self.assertTrue((root/'ЗАПУСТИТЬ_QX.cmd').is_file())
        self.assertIn('qx_icon.ico', shortcut)
        self.assertIn('Start Menu', shortcut)
        self.assertNotIn('START_QX_MODERN.bat', shortcut)
