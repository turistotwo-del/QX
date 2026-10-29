"""Regression coverage for 4.0.27 first-run Windows embeddable Python failure.

The embedded interpreter reads only python312._pth, so the source root must
be explicitly included even when qx_entry.py is the entry script.
"""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / 'portable' / 'start_qx.ps1').read_text(encoding='utf-8-sig')


class PortablePythonPathRecovery(unittest.TestCase):
    def test_embeddable_pth_adds_relative_source_root(self):
        self.assertIn('Lib\\site-packages`r`n..\\..`r`nimport site', SCRIPT)
        self.assertIn("$null = Repair-QXModulePath", SCRIPT)
        self.assertLess(SCRIPT.index('$null = Repair-QXModulePath'), SCRIPT.index("Download-Https 'https://bootstrap.pypa.io/get-pip.py'"))

    def test_existing_runtime_selfcheck_before_any_download(self):
        self.assertLess(SCRIPT.index("Write-Host '[QX] Checking the existing runtime"),
                        SCRIPT.index("Write-Host '[QX] Setting up the private Python runtime"))
        self.assertIn("Write-Host '[QX] Reusing installed Python and dependencies.'", SCRIPT)
        self.assertIn("[IO.File]::WriteAllText($ready, 'QX Portable runtime verified')", SCRIPT)
        self.assertIn('if ($needsSetup) {', SCRIPT)

    def test_isolated_python_can_import_qx_when_root_exposed(self):
        # Python -I models the crucial embedded behavior (no script directory
        # inherited from PYTHONPATH); Windows _pth supplies the relative root.
        code = ('import sys,runpy;'
                'sys.path.insert(0,'+repr(str(ROOT))+');'
                "sys.argv=['qx_entry.py','--selfcheck'];"
                'runpy.run_path('+repr(str(ROOT / 'qx_entry.py'))+",run_name='__main__')")
        p = subprocess.run([sys.executable, '-I', '-c', code], cwd=ROOT.parent,
                           capture_output=True, text=True, timeout=40)
        self.assertEqual(p.returncode, 0, p.stdout+'\n'+p.stderr)
        self.assertIn('QX selfcheck: OK', p.stdout)

if __name__ == '__main__':
    unittest.main()
