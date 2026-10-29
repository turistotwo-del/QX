"""Run the actual frontend queue with deterministic timers and delayed API replies."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TenderFieldBatchTests(unittest.TestCase):
    def test_rapid_edits_serialization_retry_and_card_isolation(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for the frontend regression checks')
        result = subprocess.run(
            [node, str(ROOT / 'tests/tender_field_batch.cjs'), str(ROOT / 'modern/web/app.ts')],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Tender field batch regressions: 6 passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
