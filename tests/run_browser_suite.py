"""Isolated Chromium acceptance runner.

Each case runs in its own OS process group, with stdout redirected to an
actual temporary file (never a PIPE). Chromium grandchildren sometimes inherit
stdout: ``Popen.communicate`` then waits for pipe EOF *after* the Python test
has exited. ``wait()`` plus a disk-backed log avoids that deadlock while still
enforcing a per-case deadline and capturing the final test output.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    'browser_eis_jobs_4040.py',
    'browser_workspace_4039.py',
    'browser_selective_repair.py',
    'browser_smoke.py',
    'browser_tz_multi_ai.py',
    'browser_ai_offline.py',
    'browser_gguf_status.py',
    'browser_eis_lookup.py',
    'browser_eis_document_url.py',
    'browser_eis_bulk.py',
    'browser_package_import.py',
    'browser_restore.py',
    'browser_diagnostics.py',
    'browser_legacy_import.py',
)


def _terminate_tree(process: subprocess.Popen) -> None:
    """Stop orphan Chromium children and do not wait for inherited stdout."""
    if os.name == 'nt':
        # /T targets child processes even if the Python process has exited.
        # In practice test scenarios also close their browser contexts.
        try:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=4, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _log_tail(stream, limit: int = 5000) -> str:
    stream.flush()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(max(0, size - limit), os.SEEK_SET)
    return stream.read().decode('utf-8', errors='replace').strip()


def run_check(command: list[str], timeout: int, *, cwd: Path = ROOT,
              env: dict[str, str] | None = None) -> tuple[bool, bool, int | None, str, float]:
    """Return (passed, timed_out, returncode, output, elapsed).

    Do not mistake a printed PASS for success: the direct test process must
    exit with code zero within the deadline. Stdout from background browser
    descendants cannot delay this judgement.
    """
    started = time.monotonic()
    process = None
    expired = False
    exitcode = None
    with tempfile.TemporaryFile(mode='w+b') as log:
        options = {'cwd': str(cwd), 'env': env, 'stdout': log,
                   'stderr': subprocess.STDOUT}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options['start_new_session'] = True
        try:
            process = subprocess.Popen(command, **options)
            try:
                exitcode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                expired = True
                _terminate_tree(process)
                try:
                    exitcode = process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    exitcode = process.wait(timeout=3)
        finally:
            if process is not None:
                # Reap any browsers that survived their parent on POSIX. A
                # previous PASS must not leave Chromium running for the next
                # test, nor hold a pipe open in the caller.
                if os.name != 'nt' or expired:
                    _terminate_tree(process)
        output = _log_tail(log, limit=5000 if not expired else 1500)
    return (not expired and exitcode == 0, expired, exitcode, output,
            time.monotonic() - started)


def main() -> int:
    parser = argparse.ArgumentParser(description='Isolated QX browser acceptance suite')
    parser.add_argument('--timeout', type=int, default=60)
    parser.add_argument('--only', choices=SCENARIOS, default=None)
    args = parser.parse_args()
    if not 5 <= args.timeout <= 600:
        parser.error('Timeout must be 5..600 seconds')

    cases = (args.only,) if args.only else SCENARIOS
    failures = []
    for name in cases:
        env = dict(os.environ, QX_OFFLINE_MODE='1')
        env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
        print(f'[QX Chromium] Starting {name}', flush=True)
        try:
            passed, expired, code, output, elapsed = run_check(
                [sys.executable, '-u', str(ROOT / 'tests' / name)],
                timeout=args.timeout, cwd=ROOT, env=env)
            if output:
                print(output, flush=True)
            status = 'TIMEOUT' if expired else 'PASS' if passed else 'FAIL'
            print(f'[QX Chromium] {status} {name}, exit={code}, {elapsed:.1f}s', flush=True)
            if not passed:
                failures.append(name)
        except (OSError, subprocess.SubprocessError) as error:
            print(f'[QX Chromium] ERROR {name}: {error}', flush=True)
            failures.append(name)
    print(f'[QX Chromium] {len(cases)-len(failures)} passed; {len(failures)} failed', flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
