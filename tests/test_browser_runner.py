"""Regressions for cases that printed PASS but left the test runner hanging."""
import os
import sys
import time
import unittest
from pathlib import Path

from run_browser_suite import run_check


class BrowserRunnerTests(unittest.TestCase):
    def test_success_with_inherited_stdout_from_grandchild(self):
        # On POSIX, the test exits instantly, while the background subprocess
        # retains its stdout for 25s. A communicate()-based runner would hang.
        code = ("import subprocess,sys; "
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(25)']); "
                "print('BROWSER_OK',flush=True)")
        start = time.monotonic()
        good, timed_out, exitcode, output, _ = run_check(
            [sys.executable, '-u', '-c', code], 5)
        self.assertTrue(good)
        self.assertFalse(timed_out)
        self.assertEqual(exitcode, 0)
        self.assertIn('BROWSER_OK', output)
        self.assertLess(time.monotonic() - start, 4)

    def test_nonzero_exit_is_failed_even_if_pass_printed(self):
        result = run_check([sys.executable, '-c', "print('PASS');raise SystemExit(5)"], 5)
        self.assertFalse(result[0])
        self.assertFalse(result[1])
        self.assertEqual(result[2], 5)

    def test_timeout_returns_failure(self):
        result = run_check([sys.executable, '-u', '-c',
                            "import time;print('PASS',flush=True);time.sleep(30)"], 1)
        self.assertFalse(result[0])
        self.assertTrue(result[1])
        self.assertIn('PASS', result[3])

    def test_log_tail_bounded(self):
        result = run_check([sys.executable, '-c',
                            "print('a'*30000);print('TAIL_MARKER')"], 5)
        self.assertTrue(result[0])
        self.assertLessEqual(len(result[3]), 5000)
        self.assertIn('TAIL_MARKER', result[3])


if __name__ == '__main__':
    unittest.main()
