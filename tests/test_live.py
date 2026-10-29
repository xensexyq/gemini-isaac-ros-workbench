"""Container lifecycle regression checks; no Docker daemon or hardware required."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LiveLifecycleTests(unittest.TestCase):
    def run_stop(self, label):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            fake = path / 'docker'
            fake.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
state = Path(os.environ['FAKE_DOCKER_STATE'])
a = sys.argv[1:]
if a[0] == 'inspect':
    if state.exists():
        # One stale successful inspect can race with automatic removal.
        sys.exit(1 if '--format' in a else 0)
    if '--format' in a:
        field = a[a.index('--format') + 1]
        print('true' if 'AutoRemove' in field else os.environ['FAKE_DOCKER_LABEL'])
    sys.exit(0)
if a[0] == 'stop':
    state.write_text('automatically removed')
    print('gemini-isaac-ros-live')
    sys.exit(0)
if a[0] == 'rm':
    # Reproduce an inspect that succeeds while auto-removal races with rm.
    print('No such container', file=sys.stderr)
    sys.exit(1)
sys.exit(2)
''')
            fake.chmod(0o755)
            env = dict(os.environ, PATH=str(path) + os.pathsep + os.environ['PATH'],
                       FAKE_DOCKER_STATE=str(path / 'removed'), FAKE_DOCKER_LABEL=label)
            result = subprocess.run(['bash', str(ROOT / 'scripts/live.sh'), 'stop'],
                                    env=env, text=True, capture_output=True)
            return result, (path / 'removed').exists()

    def test_auto_removed_container_stop_succeeds(self):
        result, removed = self.run_stop('gemini-isaac-ros-workbench-v1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(removed)
        self.assertNotIn('No such container', result.stderr)

    def test_stop_rejects_unrelated_container(self):
        result, removed = self.run_stop('another-project')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(removed)


if __name__ == '__main__':
    unittest.main()
