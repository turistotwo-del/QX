"""Release-artifact verification for the Windows QX installer.

This is intentionally run *after* Windows CI has installed, upgraded and
uninstalled the built installer. A build that fails acceptance must not be
published as a normal installer artifact.

The manifest and SHA256SUMS file help detect accidental file corruption. They
are NOT a substitute for Authenticode/code signing or a trusted distribution
channel.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from modern.release_info import APP_VERSION, BUILD_CHANNEL, SETUP_BASENAME

MANIFEST_NAME = 'QX_build_manifest.json'
SUMS_NAME = 'SHA256SUMS.txt'
EXPECTED_GATES = (
    'python-unit-tests', 'legacy-engine-tests', 'browser-acceptance',
    'installed-app-selfcheck', 'installed-http-api-selfcheck',
    'installed-ai-runtime-selfcheck', 'legacy-profile-migration',
    'reinstallation', 'uninstallation', 'user-data-preservation',
)


class ReleaseGateError(ValueError):
    """A build should not be published as a release artifact."""


def _expected_name() -> str:
    return SETUP_BASENAME + '.exe'


def _read_installer(installer: Path) -> tuple[str, int]:
    if installer.name != _expected_name():
        raise ReleaseGateError('Installer filename does not match the current QX release')
    if not installer.is_file() or installer.is_symlink():
        raise ReleaseGateError('Expected regular Windows installer file is missing')
    size = installer.stat().st_size
    if size < 1_000_000:
        raise ReleaseGateError('Installer is unexpectedly small; refusing publication')
    # Inno Setup installers are portable executable (PE) files, not ZIPs.
    with installer.open('rb') as stream:
        header = stream.read(64)
        if len(header) < 64 or header[:2] != b'MZ':
            raise ReleaseGateError('Installer does not have a Windows MZ header')
        pe_offset = int.from_bytes(header[0x3c:0x40], 'little')
        if not (64 <= pe_offset < min(size - 4, 8 * 1024 * 1024)):
            raise ReleaseGateError('Invalid PE header offset')
        stream.seek(pe_offset)
        if stream.read(4) != b'PE\0\0':
            raise ReleaseGateError('Installer does not contain a valid PE signature')
        stream.seek(0)
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return digest, size


def create_manifest(installer: Path, *, ci: bool = False) -> dict:
    """Produce a manifest, only after the Windows acceptance job succeeds.

    `ci` must be explicitly set by the CI runner after successful install,
    reinstallation, data-preservation verification and uninstall. A caller
    cannot bypass a failed CI step, because GitHub Actions stops that step.
    """
    if not ci:
        raise ReleaseGateError('Release artifacts may be marked verified only by CI after acceptance')
    digest, size = _read_installer(installer)
    return {
        'schema': 'QX-Windows-Release-Manifest-v1',
        'application': 'QX Подборщик Modern',
        'version': APP_VERSION,
        'channel': BUILD_CHANNEL,
        'installer': installer.name,
        'size_bytes': size,
        'sha256': digest,
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'ci_gates_passed': list(EXPECTED_GATES),
        'signed': False,
        'note': 'Checksums detect corruption. This preview build is not Authenticode signed.',
    }


def write_manifest(installer: Path, *, ci: bool = False) -> Path:
    manifest = create_manifest(installer, ci=ci)
    location = installer.parent / MANIFEST_NAME
    sums = installer.parent / SUMS_NAME
    location.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sums.write_text(f"{manifest['sha256']} *{manifest['installer']}\n", encoding='ascii')
    verify_manifest(installer)
    return location


def verify_manifest(installer: Path) -> dict:
    manifest_file = installer.parent / MANIFEST_NAME
    sums_file = installer.parent / SUMS_NAME
    try:
        manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
        sums = sums_file.read_text(encoding='ascii')
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseGateError('Manifest and/or checksum file is missing or invalid') from exc
    if not isinstance(manifest, dict):
        raise ReleaseGateError('Invalid release manifest')
    expected = {'schema':'QX-Windows-Release-Manifest-v1',
                'version': APP_VERSION, 'channel': BUILD_CHANNEL,
                'installer': _expected_name(), 'ci_gates_passed': list(EXPECTED_GATES)}
    for key, val in expected.items():
        if manifest.get(key) != val:
            raise ReleaseGateError('Release manifest mismatch: ' + key)
    sha, size = _read_installer(installer)
    if manifest.get('size_bytes') != size or manifest.get('sha256') != sha:
        raise ReleaseGateError('Installer checksum or size does not match release manifest')
    if not re.fullmatch(r'[0-9a-f]{64}', sha):
        raise ReleaseGateError('Invalid SHA-256 digest')
    if sums != f'{sha} *{installer.name}\n':
        raise ReleaseGateError('SHA256SUMS.txt differs from the installer')
    return manifest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['create','verify'])
    p.add_argument('--installer', type=Path, default=PROJECT_ROOT / 'windows_build' / 'out' / _expected_name())
    p.add_argument('--ci-accepted', action='store_true', help='Only after Windows acceptance steps have succeeded')
    args = p.parse_args()
    try:
        if args.command == 'create':
            write_manifest(args.installer, ci=args.ci_accepted)
        else:
            verify_manifest(args.installer)
    except (ReleaseGateError, OSError) as exc:
        print('QX release gate FAILED:', exc, file=sys.stderr)
        return 1
    print('QX release gate OK:', args.installer.name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
