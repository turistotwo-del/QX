"""Prevent a failed Windows build from being published as a QX installer."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'windows-build.yml'
BUILD_SCRIPT = ROOT / 'windows_build' / 'build_windows.ps1'


class ReleaseCIPolicy(unittest.TestCase):
    def test_artifact_uploaded_only_after_success(self):
        s=WORKFLOW.read_text(encoding='utf-8')
        upload=s.rsplit('- uses: actions/upload-artifact@v4',1)[-1]
        self.assertIn('if: success()',upload)
        self.assertNotIn('if: always()',upload)
        self.assertIn('QX_build_manifest.json',upload)
        self.assertIn('SHA256SUMS.txt',upload)

    def test_windows_checks_run_before_release_manifest(self):
        s=WORKFLOW.read_text(encoding='utf-8')
        self.assertLess(s.index('Install, selfcheck, upgrade, uninstall'),s.index('release_gate.py create --ci-accepted'))
        self.assertLess(s.index('release_gate.py create --ci-accepted'),s.index('actions/upload-artifact@v4'))
        for step in ('--api-selfcheck','--ai-selfcheck','ci_upgrade_fixture.py verify',
                     'unins000.exe','--profile-selfcheck'):
            self.assertIn(step,s)

    def test_gui_executables_are_not_checked_as_console_commands(self):
        workflow=WORKFLOW.read_text(encoding='utf-8')
        recipe=BUILD_SCRIPT.read_text(encoding='utf-8')
        helper=(ROOT/'windows_build'/'invoke_checked_exe.ps1').read_text(encoding='utf-8')
        self.assertIn('Invoke-QXCheck -ExePath $app',workflow)
        self.assertIn('Invoke-QXCheck -ExePath $exe',recipe)
        self.assertNotIn('          & $app --',workflow)
        self.assertNotIn('\n& $exe --',recipe)
        self.assertIn('WaitForExit(',helper)
        self.assertIn('ExitCode -ne 0',helper)
        self.assertIn('timed out after',helper)

    def test_stale_installer_deleted_before_compiler(self):
        s=BUILD_SCRIPT.read_text(encoding='utf-8')
        self.assertLess(s.index('Remove-Item -LiteralPath $previousInstaller'),
                        s.index('Creating the installer with Inno Setup'))
        self.assertIn('Remove-Item -LiteralPath $stalePath',s)


if __name__=='__main__':unittest.main()
