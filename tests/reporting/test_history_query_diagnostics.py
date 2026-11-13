"""The worker retains native diagnostics even when a query never responds."""
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "posix" and importlib.util.find_spec("numpy"),
                     "POSIX process groups and NumPy required")
class HistoryQueryDiagnosticsTest(unittest.TestCase):
    def test_killed_query_keeps_native_stderr_in_supervised_worker_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            ready = path / "native-ready"
            native = path / "native"
            native.write_text(
                f"#!{sys.executable}\n"
                "import os, pathlib, signal, sys\n"
                "sys.stdin.readline()\n"
                "os.write(2, b'native-query-diagnostic-before-kill\\n')\n"
                f"pathlib.Path({str(ready)!r}).write_text('ready')\n"
                "signal.pause()\n", encoding="utf-8")
            native.chmod(0o700)
            worker = (
                "import sys\n"
                f"sys.path.insert(0, {str(ROOT / 'benchmarks/reporting/closed_loop')!r})\n"
                "from contracts import load_task, manifest_sha256\n"
                "from history_policy import HistoryPolicy\n"
                "task = load_task('syn-nl-lv-01')\n"
                "policy = HistoryPolicy(task, manifest_sha256(task), "
                "'native-continuous-affine-history-ipopt/1', "
                "task['control_domains']['continuous']['problem_id'])\n"
                "policy.query(task['task_id'], "
                "[row['initial'] for row in task['model']['states']], 0)\n"
            )
            env = {**os.environ, "CSL_NATIVE_POLICY_BRIDGE": str(native)}
            process = subprocess.Popen([sys.executable, "-c", worker], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True)
            try:
                deadline = time.monotonic() + 15
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists(), "native query did not reach the pending-response state")
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(stdout, b"")
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertIn(b"native-query-diagnostic-before-kill\n", stderr)
