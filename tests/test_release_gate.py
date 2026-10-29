"""Cross-platform tests of the release-gating script (no Windows SDK needed)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from windows_build import release_gate as gate


def fake_pe(path):
    content = bytearray(1_000_400)
    content[0:2] = b'MZ'
    content[0x3c:0x40] = (0x80).to_bytes(4,'little')
    content[0x80:0x84] = b'PE\0\0'
    path.write_bytes(content)


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='qx_release_')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.exe = self.base / (gate.SETUP_BASENAME+'.exe')
        fake_pe(self.exe)

    def test_round_trip_manifest(self):
        gate.write_manifest(self.exe, ci=True)
        data = gate.verify_manifest(self.exe)
        self.assertEqual(data['version'], gate.APP_VERSION)
        self.assertEqual(len(data['sha256']), 64)
        self.assertFalse(data['signed'])

    def test_refuse_marking_accepted_without_ci(self):
        with self.assertRaises(gate.ReleaseGateError):
            gate.write_manifest(self.exe)
        self.assertFalse((self.base / gate.MANIFEST_NAME).exists())

    def test_refuse_wrong_name(self):
        other = self.base / 'QX_Setup_stale.exe'
        other.write_bytes(self.exe.read_bytes())
        with self.assertRaises(gate.ReleaseGateError):
            gate.write_manifest(other, ci=True)

    def test_refuse_zip_disguised_as_exe(self):
        self.exe.write_bytes(b'PK' + b'0' * 1_000_500)
        with self.assertRaises(gate.ReleaseGateError):
            gate.write_manifest(self.exe, ci=True)

    def test_refuse_truncated_and_invalid_pe(self):
        self.exe.write_bytes(b'MZ')
        with self.assertRaises(gate.ReleaseGateError):
            gate.write_manifest(self.exe, ci=True)
        fake_pe(self.exe)
        with self.exe.open('r+b') as f:
            f.seek(0x80)
            f.write(b'XXXX')
        with self.assertRaises(gate.ReleaseGateError):
            gate.write_manifest(self.exe, ci=True)

    def test_refuse_modified_installer(self):
        gate.write_manifest(self.exe, ci=True)
        with self.exe.open('r+b') as f:
            f.seek(1234)
            f.write(b'CORRUPTED')
        with self.assertRaisesRegex(gate.ReleaseGateError, 'checksum'):
            gate.verify_manifest(self.exe)

    def test_refuse_changed_release_metadata(self):
        gate.write_manifest(self.exe, ci=True)
        manifest_file = self.base / gate.MANIFEST_NAME
        obj = json.loads(manifest_file.read_text(encoding='utf-8'))
        obj['version'] = '4.0.11'
        manifest_file.write_text(json.dumps(obj),encoding='utf-8')
        with self.assertRaisesRegex(gate.ReleaseGateError, 'version'):
            gate.verify_manifest(self.exe)

    def test_refuse_mismatching_checksum_list(self):
        gate.write_manifest(self.exe, ci=True)
        (self.base / gate.SUMS_NAME).write_text('0'*64 + ' *'+self.exe.name+'\n',encoding='ascii')
        with self.assertRaisesRegex(gate.ReleaseGateError, 'SHA256SUMS'):
            gate.verify_manifest(self.exe)

    def test_refuse_absent_manifest(self):
        with self.assertRaises(gate.ReleaseGateError):
            gate.verify_manifest(self.exe)

    def test_reject_smaller_but_valid_pe_stub(self):
        with self.exe.open('r+b') as f:
            f.truncate(1024)
        with self.assertRaisesRegex(gate.ReleaseGateError, 'small'):
            gate.write_manifest(self.exe, ci=True)


if __name__ == '__main__': unittest.main()
