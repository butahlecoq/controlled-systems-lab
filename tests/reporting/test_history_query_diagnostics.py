"""The worker retains native diagnostics even when a query never responds."""
import importlib.util
import json
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
        self._check_killed_query("history_policy", "HistoryPolicy",
                                 "native-continuous-affine-history-ipopt/1", "continuous")

    def test_killed_finite_policy_query_keeps_native_stderr_in_supervised_worker_stream(self):
        receipt = self._check_killed_query(
            "native_graph_policy", "NativeGraphPolicy",
            "native-parallelotope-fixed-plan-mpc/1", "finite")
        self.assertIn("shared across native queries", receipt["native_stderr"])
        self.assertIn("not isolated per call", receipt["native_stderr"])

    def _check_killed_query(self, module, policy_type, controller_id, action_domain):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            ready = path / "native-ready"
            receipt = path / "preparation-receipt.json"
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
                "import json, pathlib, sys\n"
                f"sys.path.insert(0, {str(ROOT / 'benchmarks/reporting/closed_loop')!r})\n"
                "from contracts import load_task, manifest_sha256\n"
                f"from {module} import {policy_type}\n"
                "task = load_task('syn-nl-lv-01')\n"
                f"policy = {policy_type}(task, manifest_sha256(task), {controller_id!r}, "
                f"task['control_domains'][{action_domain!r}]['problem_id'])\n"
                f"pathlib.Path({str(receipt)!r}).write_text(json.dumps(policy.preparation_receipt))\n"
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
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(stdout, b"")
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertIn(b"native-query-diagnostic-before-kill\n", stderr)
            return json.loads(receipt.read_text())
