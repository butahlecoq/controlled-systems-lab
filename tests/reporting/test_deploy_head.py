"""Exercise the Pages deployment freshness gate against an HTTP endpoint."""

import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reports" / "check_deploy_head.py"
OLDER = "1" * 40
NEWER = "2" * 40


class BranchHandler(http.server.BaseHTTPRequestHandler):
    current_sha = NEWER
    response_code = 200

    def do_GET(self):
        if self.path != "/repos/example/reports/branches/main":
            self.send_error(404)
            return
        payload = json.dumps({"commit": {"sha": self.current_sha}}).encode()
        self.send_response(self.response_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass


class DeploymentHeadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), BranchHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join()

    def setUp(self):
        BranchHandler.current_sha = NEWER
        BranchHandler.response_code = 200

    def run_gate(self, expected_sha):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "github-output"
            env = os.environ.copy()
            env.update(
                {
                    "GITHUB_API_URL": f"http://127.0.0.1:{self.server.server_port}",
                    "GITHUB_REPOSITORY": "example/reports",
                    "GITHUB_TOKEN": "test-token",
                    "GITHUB_SHA": expected_sha,
                    "GITHUB_OUTPUT": str(output),
                }
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT)],
                env=env,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result, output.read_text() if output.exists() else ""

    def test_later_validation_of_older_run_cannot_deploy_after_newer_run(self):
        newer, newer_output = self.run_gate(NEWER)
        older, older_output = self.run_gate(OLDER)
        self.assertEqual(newer.returncode, 0, newer.stderr)
        self.assertEqual(newer_output, "current=true\n")
        self.assertEqual(older.returncode, 0, older.stderr)
        self.assertEqual(older_output, "current=false\n")

    def test_api_failure_blocks_deployment(self):
        BranchHandler.response_code = 503
        result, output = self.run_gate(NEWER)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, "")

    def test_malformed_branch_response_blocks_deployment(self):
        BranchHandler.current_sha = "not-a-commit"
        result, output = self.run_gate(NEWER)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
