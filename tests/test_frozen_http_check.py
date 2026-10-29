"""Real socket integration test. The installed EXE runs this same check in CI."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestFrozenHttpCheck(unittest.TestCase):
    def test_api_runs_with_private_database_and_leaves_user_files_untouched(self):
        with tempfile.TemporaryDirectory(prefix='qx_ci_fake_user_') as temp:
            appdata=Path(temp)
            legacy=appdata/'QX_Selector'
            legacy.mkdir()
            marker=legacy/'existing_data.txt'
            marker.write_text('DO NOT TOUCH',encoding='utf-8')
            env=os.environ.copy()
            env['LOCALAPPDATA']=str(appdata)
            env['APPDATA']=str(appdata)
            env.pop('QX_DATA_DIR',None)
            env.pop('QX_CATALOG_DIR',None)
            process=subprocess.run([sys.executable,str(ROOT/'qx_entry.py'),'--api-selfcheck'],
                cwd=str(ROOT),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                text=True,timeout=35)
            self.assertEqual(process.returncode,0,process.stdout+'\n'+process.stderr)
            self.assertIn('QX frozen HTTP selfcheck: OK',process.stdout)
            self.assertEqual(marker.read_text(encoding='utf-8'),'DO NOT TOUCH')
            self.assertEqual(sorted(p.name for p in legacy.iterdir()),['existing_data.txt'])
            self.assertFalse((appdata/'QXPodborshchik').exists())


if __name__=='__main__':
    unittest.main()
