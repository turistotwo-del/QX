"""Packaged Windows QX must not try to write its user catalog into the EXE bundle."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class FrozenUserCatalogTests(unittest.TestCase):
    def test_portable_snapshot_resides_in_user_data_for_frozen_app(self):
        with tempfile.TemporaryDirectory() as data:
            env=os.environ.copy()
            env['QX_DATA_DIR']=data
            script='''import sys
sys.frozen = True
from core import user_catalog
from pathlib import Path
assert user_catalog.PORTABLE_DB == Path(sys.argv[1]) / 'QX_UserData' / 'QX_UserCatalog.qxdb'
assert user_catalog.sync_catalogs()['portable_ok']
assert user_catalog.PORTABLE_DB.is_file()
'''
            p=subprocess.run([sys.executable,'-c',script,data],cwd=ROOT,
                            env=env,capture_output=True,text=True,timeout=12)
            self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)


if __name__=='__main__': unittest.main()
