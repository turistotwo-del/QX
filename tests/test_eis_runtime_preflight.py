"""Portable upgrades must discover missing EIS libraries despite an old ready marker."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import importlib
import os
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

import qx_entry

ROOT = Path(__file__).resolve().parents[1]


class EisRuntimePreflight(unittest.TestCase):
    def test_missing_xml_dependency_fails_preflight_without_leaking_details(self):
        real_import = importlib.import_module
        def missing(module, *args, **kwargs):
            if module == 'defusedxml':
                raise ModuleNotFoundError('private path and token must not be printed')
            return real_import(module, *args, **kwargs)
        err = StringIO()
        with patch('importlib.import_module', side_effect=missing), redirect_stderr(err):
            status = qx_entry.eis_dependency_selfcheck()
        self.assertEqual(status, 1)
        self.assertIn('ModuleNotFoundError', err.getvalue())
        self.assertIn('repair', err.getvalue())
        self.assertNotIn('private path and token', err.getvalue())

    def test_full_selfcheck_also_requires_eis_dependencies(self):
        out = StringIO()
        with patch.dict(os.environ, {}), patch.object(qx_entry, '_load_eis_dependencies', side_effect=ModuleNotFoundError('defusedxml')), redirect_stderr(out):
            self.assertEqual(qx_entry.selfcheck(), 1)
        self.assertIn('defusedxml', out.getvalue())

    def test_successful_preflight_never_opens_network_or_changes_user_files(self):
        with tempfile.TemporaryDirectory(prefix='qx_eis_preflight_') as tmp:
            sentinel = Path(tmp) / 'existing-user-data.txt'
            sentinel.write_text('preserve this')
            out = StringIO()
            with patch.dict(os.environ, {'QX_DATA_DIR': tmp, 'QX_CATALOG_DIR': tmp}), \
                 patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('Unexpected network access')), \
                 redirect_stdout(out):
                self.assertEqual(qx_entry.eis_dependency_selfcheck(), 0)
            self.assertEqual(sentinel.read_text(), 'preserve this')
            self.assertEqual([p.name for p in Path(tmp).iterdir()], [sentinel.name])
            self.assertIn('QX EIS dependencies: OK', out.getvalue())

    def test_fresh_process_probe_uses_a_disposable_profile(self):
        with tempfile.TemporaryDirectory(prefix='qx_eis_real_profile_') as tmp:
            original = Path(tmp)
            sentinel = original / 'existing.txt'
            sentinel.write_text('original user profile')
            environment = {**os.environ, 'QX_DATA_DIR': tmp, 'QX_CATALOG_DIR': tmp,
                           'QX_PORTABLE_DATA_DIR': tmp, 'QX_OFFLINE_MODE': '1'}
            result = subprocess.run([sys.executable, str(ROOT / 'qx_entry.py'), '--eis-selfcheck'],
                                    cwd=ROOT, env=environment, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(sorted(p.name for p in original.iterdir()), ['existing.txt'])
            self.assertEqual(sentinel.read_text(), 'original user profile')

    def test_portable_preflight_is_unconditional_before_marker_reuse_decision(self):
        script = (ROOT / 'portable/start_qx.ps1').read_text(encoding='utf-8-sig')
        before_setup = script.index('    if ($needsSetup) {')
        preflight = script.index("'qx_entry.py') --eis-selfcheck")
        decision = script.index('    $needsSetup =')
        self.assertLess(preflight, decision)
        self.assertLess(decision, before_setup)
        self.assertIn('-or !$eisDependenciesReady', script[decision:before_setup])
        self.assertIn("'ready-4.0.25.marker'", script)
        self.assertIn('-and $eisDependenciesReady -and', script[decision:before_setup])
        self.assertIn('Required EIS libraries', (ROOT / 'qx_entry.py').read_text())

    def test_cli_check_uses_preflight_and_never_starts_desktop(self):
        with patch('sys.argv', ['qx_entry.py', '--eis-selfcheck']), \
             patch.object(qx_entry, 'eis_dependency_selfcheck', return_value=0) as check, \
             patch.object(qx_entry, 'run_desktop') as desktop:
            self.assertEqual(qx_entry.main(), 0)
        check.assert_called_once_with()
        desktop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
