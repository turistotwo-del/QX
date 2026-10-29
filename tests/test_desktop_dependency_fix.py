"""Regression checks for Windows PowerShell portable pywebview bootstrap."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DesktopDependencyFixTests(unittest.TestCase):
    def test_no_powershell_python_c_quote_mangling(self):
        s = (ROOT/'portable/start_qx.ps1').read_text('utf-8-sig')
        self.assertIn("$desktopProbe = Join-Path $PSScriptRoot 'desktop_probe.py'", s)
        self.assertIn('& $python $desktopProbe --check', s)
        self.assertNotIn('& $python -c ', s)

    def test_allows_source_only_proxy_tools(self):
        s = (ROOT/'portable/start_qx.ps1').read_text('utf-8-sig')
        install = next(x for x in s.splitlines() if '-m pip install' in x and 'requirements_desktop.txt' in x)
        self.assertIn('--prefer-binary', install)
        self.assertIn('--no-build-isolation', install)
        self.assertNotIn('--only-binary', install)
        req = (ROOT/'portable/requirements_desktop.txt').read_text('utf-8')
        self.assertIn('pywebview==6.2.1', req)
        self.assertIn('proxy-tools', req)

    def test_embedded_python_installs_build_tools_first(self):
        s = (ROOT/'portable/start_qx.ps1').read_text('utf-8-sig')
        build_tools = next(x for x in s.splitlines() if '-m pip install' in x and "'setuptools>=70,<85'" in x)
        install = next(x for x in s.splitlines() if '-m pip install' in x and 'requirements_desktop.txt' in x)
        self.assertIn('--only-binary=:all:', build_tools)
        self.assertIn("'wheel>=0.45,<1'", build_tools)
        self.assertIn('--no-build-isolation', install)
        self.assertLess(s.index(build_tools), s.index('& $python $desktopProbe --build-check'))
        self.assertLess(s.index('& $python $desktopProbe --build-check'), s.index(install))

    def test_build_backend_probe_is_independent_from_webview(self):
        script = ROOT/'portable/desktop_probe.py'
        proc = subprocess.run([sys.executable, str(script), '--build-check'], capture_output=True, text=True)
        # The test machine may not include the wheel library; the command must
        # still return a controlled result rather than a traceback.
        self.assertIn(proc.returncode, (0, 1))
        self.assertIn('Private Python build backend:', proc.stdout + proc.stderr)
        source = script.read_text('utf-8')
        self.assertIn('import setuptools.build_meta', source)
        self.assertIn('import wheel', source)
        self.assertIn('def build_check()', source)

    def test_probe_is_standalone_and_does_not_download(self):
        script = ROOT/'portable/desktop_probe.py'
        proc = subprocess.run([sys.executable, str(script), '--help'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('--check', proc.stdout)
        source = script.read_text('utf-8')
        self.assertIn('import webview', source)
        self.assertIn('import clr', source)
        self.assertNotIn('pip install', source)

    def test_preserves_runtime_and_ai(self):
        s = (ROOT/'portable/start_qx.ps1').read_text('utf-8-sig')
        self.assertIn("$runtime = Join-Path $root '.qx_runtime'",s)
        self.assertIn("$aiBase = Join-Path $env:LOCALAPPDATA 'QXPodborshchik\QX_AI'",s)
        self.assertIn("desktop-webview2-4.0.29.marker",s)
        self.assertIn('Repair-QXModulePath',s)

if __name__ == '__main__':
    unittest.main()
