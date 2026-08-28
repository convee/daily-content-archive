import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "scripts" / "archive_lock.py"


class ArchiveLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        (self.repo / ".git").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def run_lock(self, *args):
        return subprocess.run([sys.executable, str(LOCK), "--repo", str(self.repo)] + list(args), text=True, capture_output=True)

    def test_owner_controls_lease(self):
        acquired = self.run_lock("acquire", "--name", "twitter", "--owner", "run-a", "--ttl", "120")
        self.assertEqual(acquired.returncode, 0)
        self.assertTrue(json.loads(acquired.stdout)["acquired"])
        busy = self.run_lock("acquire", "--name", "twitter", "--owner", "run-b", "--ttl", "120")
        self.assertEqual(busy.returncode, 3)
        wrong = self.run_lock("release", "--name", "twitter", "--owner", "run-b")
        self.assertEqual(wrong.returncode, 5)
        released = self.run_lock("release", "--name", "twitter", "--owner", "run-a")
        self.assertEqual(released.returncode, 0)


class RepositoryHealthTests(unittest.TestCase):
    def test_repository_has_no_integrity_errors(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "archive_health.py"), "--repo", str(ROOT)], text=True, capture_output=True)
        if result.returncode:
            self.fail(result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
