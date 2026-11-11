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
    latest_report_id = 42

    def do_GET(self):
        if self.path.startswith("/repos/example/reports/actions/workflows/algorithm-reports.yml/runs?"):
            payload = {"workflow_runs": [{
                "id": self.latest_report_id,
                "head_sha": NEWER,
                "head_branch": "main",
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-11-03T03:00:00Z",
            }]}
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
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
        BranchHandler.latest_report_id = 42

    def run_gate(self, expected_sha, source_run_id=None, *, check_only=False, create_site=True):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "github-output"
            site = Path(temporary) / "site"
            if create_site:
                site.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "GITHUB_API_URL": f"http://127.0.0.1:{self.server.server_port}",
                    "GITHUB_REPOSITORY": "example/reports",
                    "GITHUB_TOKEN": "test-token",
                    "GITHUB_SHA": expected_sha,
                    "GITHUB_OUTPUT": str(output),
                    "PAGES_SITE_DIR": str(site),
                }
            )
            if source_run_id is not None:
                event = Path(temporary) / "event.json"
                event.write_text(json.dumps({"workflow_run": {
                    "id": source_run_id,
                    "name": "Algorithm report records and site",
                    "head_sha": expected_sha,
                    "head_branch": "main",
                    "status": "completed",
                    "conclusion": "success",
                }}))
                env["GITHUB_EVENT_PATH"] = str(event)
            command = [sys.executable, str(SCRIPT)]
            if check_only:
                command.append("--check-only")
            result = subprocess.run(
                command,
                env=env,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            marker_path = site / "pages-augmentation-source.json"
            marker = json.loads(marker_path.read_text()) if marker_path.exists() else None
            return result, output.read_text() if output.exists() else "", marker

    def test_later_validation_of_older_run_cannot_deploy_after_newer_run(self):
        newer, newer_output, _ = self.run_gate(NEWER)
        older, older_output, _ = self.run_gate(OLDER)
        self.assertEqual(newer.returncode, 0, newer.stderr)
        self.assertEqual(newer_output, "current=true\n")
        self.assertEqual(older.returncode, 0, older.stderr)
        self.assertEqual(older_output, "current=false\n")

    def test_cumulative_deployer_keeps_newer_pending_when_older_validation_finishes_late(self):
        # Model GitHub's documented pending-slot semantics from the sole publisher.
        # A running old deployment holds the group while the newer, then older,
        # validated jobs arrive. Preserve the queued, newest-source publication.
        workflow = (ROOT / ".github" / "workflows" / "pages-augmentation-aggregation.yml").read_text()
        deploy = workflow.split("\n  deploy:\n", 1)[1]
        concurrency = deploy.split("\n    concurrency:\n", 1)[1].split("\n    environment:\n", 1)[0]
        settings = dict(
            line.strip().split(": ", 1)
            for line in concurrency.splitlines()
            if ": " in line
        )
        pending = [NEWER]
        if settings.get("queue", "single") == "single":
            pending = [OLDER]
        elif settings["queue"] == "max":
            pending.append(OLDER)
        else:
            self.fail("Unsupported deploy queue policy")

        published = "0" * 40  # Already-running deployment finished first.
        for commit in pending:
            result, output, _ = self.run_gate(commit)
            self.assertEqual(result.returncode, 0, result.stderr)
            if output == "current=true\n":
                published = commit
        self.assertEqual(published, NEWER)

    def test_api_failure_blocks_deployment(self):
        BranchHandler.response_code = 503
        result, output, _ = self.run_gate(NEWER)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, "")

    def test_malformed_branch_response_blocks_deployment(self):
        BranchHandler.current_sha = "not-a-commit"
        result, output, _ = self.run_gate(NEWER)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, "")

    def test_older_same_sha_report_run_cannot_deploy_after_newer_run(self):
        BranchHandler.latest_report_id = 43
        result, output, marker = self.run_gate(NEWER, source_run_id=42)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, "current=false\n")
        self.assertIsNone(marker)

    def test_current_workflow_run_writes_parent_identity_into_pages_site(self):
        result, output, marker = self.run_gate(NEWER, source_run_id=42)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("source_run_id=42\n", output)
        self.assertEqual(marker, {
            "schema": "csl.pages-augmentation-source/1",
            "report_run_id": 42,
            "head_sha": NEWER,
        })

    def test_check_only_mode_allows_freshness_check_before_site_exists(self):
        stale, stale_output, stale_marker = self.run_gate(
            OLDER, source_run_id=42, check_only=True, create_site=False)
        current, current_output, current_marker = self.run_gate(
            NEWER, source_run_id=42, check_only=True, create_site=False)
        self.assertEqual(stale.returncode, 0, stale.stderr)
        self.assertEqual(stale_output, "current=false\n")
        self.assertIsNone(stale_marker)
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertEqual(current_output, "current=true\n")
        self.assertIsNone(current_marker)


if __name__ == "__main__":
    unittest.main()
