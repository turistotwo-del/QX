"""Source-level checks only: NOT a Windows installation test."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TestWindowsBuildRecipe(unittest.TestCase):
    def test_shortcuts_match_native_taskbar_id(self):
        setup=(ROOT/'windows_build'/'QX_Setup.iss').read_text(encoding='utf-8')
        launcher=(ROOT/'modern'/'start.py').read_text(encoding='utf-8')
        self.assertEqual(setup.count('AppUserModelID: "BROKTECH.QXModern"'),2)
        self.assertIn("SetCurrentProcessExplicitAppUserModelID('BROKTECH.QXModern')",launcher)

    def test_upgrades_do_not_force_kill_application(self):
        setup=(ROOT/'windows_build'/'QX_Setup.iss').read_text(encoding='utf-8')
        self.assertIn('CloseApplications=no',setup)
        self.assertIn('AppMutex=BROKTECH.QXModern',setup)
        from modern.windows_instance import MUTEX_NAME
        self.assertEqual(MUTEX_NAME, 'BROKTECH.QXModern')
        self.assertNotIn('CloseApplications=force',setup)
        self.assertIn('PrivilegesRequired=lowest',setup)

    def test_gguf_runtime_built_and_checked_in_windows_ci(self):
        build=(ROOT/'windows_build'/'build_windows.ps1').read_text(encoding='utf-8')
        ci=(ROOT/'.github'/'workflows'/'windows-build.yml').read_text(encoding='utf-8')
        self.assertIn('https://abetlen.github.io/llama-cpp-python/whl/cpu',build)
        self.assertIn('llama-cpp-python==0.3.36',build)
        self.assertIn('QX_BUNDLE_GGUF',ci)
        self.assertIn('--ai-selfcheck',build)
        self.assertIn('--ai-selfcheck',ci)

    def test_installed_exe_migrates_and_preserves_data_in_windows_ci(self):
        ci=(ROOT/'.github'/'workflows'/'windows-build.yml').read_text(encoding='utf-8')
        entry=(ROOT/'qx_entry.py').read_text(encoding='utf-8')
        self.assertIn('ci_upgrade_fixture.py seed',ci)
        self.assertEqual(ci.count('ci_upgrade_fixture.py verify'),3)
        self.assertIn('--data-selfcheck',ci)
        self.assertIn('--data-selfcheck',entry)
        self.assertIn('QX_CI_UPGRADE_FIXTURE',ci)

    def test_setup_output_paths_agree(self):
        from modern.release_info import SETUP_BASENAME, inno_defines
        setup=(ROOT/'windows_build'/'QX_Setup.iss').read_text(encoding='utf-8')
        include=(ROOT/'windows_build'/'qx_version.iss').read_text(encoding='utf-8')
        build=(ROOT/'windows_build'/'build_windows.ps1').read_text(encoding='utf-8')
        ci=(ROOT/'.github'/'workflows'/'windows-build.yml').read_text(encoding='utf-8')
        self.assertIn('#include "qx_version.iss"',setup)
        self.assertIn('OutputBaseFilename={#QXOutputBase}',setup)
        self.assertEqual(include,inno_defines())
        self.assertIn(SETUP_BASENAME,include)
        self.assertIn('release_metadata.py',build)
        self.assertIn('release_metadata.py --print-installer',ci)
        self.assertNotIn('Preview_11.exe',ci)

if __name__=='__main__':unittest.main()
