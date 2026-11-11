import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/prepare_ccache.sh"
ACTION = ROOT / ".github/actions/native-cache-setup/action.yml"
FINISH = ROOT / ".github/actions/native-cache-finish/action.yml"


class PrepareCcacheTests(unittest.TestCase):
    def run_prepare(self, runner_os="Linux", clean="false", ccache=None, sudo_exit=1):
        with tempfile.TemporaryDirectory() as temporary:
            bindir = Path(temporary)
            output = bindir / "github-output"
            sudo = bindir / "sudo"
            sudo.write_text(
                "#!/bin/bash\n"
                "if [[ \"$*\" == *'install'* ]]; then\n"
                "  if [[ \"${MOCK_SUDO_EXIT}\" == 0 ]]; then\n"
                "    /bin/cat > \"${MOCK_BINDIR}/ccache\" <<'EOF'\n"
                "#!/bin/bash\n"
                "[[ \"$1\" == --version ]] && echo 'ccache mock 1'\n"
                "EOF\n"
                "    /bin/chmod +x \"${MOCK_BINDIR}/ccache\"\n"
                "  fi\n"
                "fi\n"
                "exit \"${MOCK_SUDO_EXIT}\"\n"
            )
            sudo.chmod(0o755)
            timeout = bindir / "timeout"
            timeout.write_text(
                "#!/bin/bash\n"
                "while [[ \"$1\" == --* ]]; do shift; done\n"
                "shift\n"
                "exec \"$@\"\n"
            )
            timeout.chmod(0o755)
            if ccache:
                binary = bindir / "ccache"
                binary.write_text("#!/bin/bash\necho 'ccache mock 1'\n")
                binary.chmod(0o755)
            env = os.environ.copy()
            env.pop("GITHUB_OUTPUT", None)
            env.update({
                "PATH": str(bindir),
                "RUNNER_OS": runner_os,
                "CACHE_CLEAN": clean,
                "GITHUB_OUTPUT": str(output),
                "MOCK_BINDIR": str(bindir),
                "MOCK_SUDO_EXIT": str(sudo_exit),
            })
            result = subprocess.run(["/bin/bash", str(SCRIPT)], text=True, capture_output=True, env=env, check=True)
            return result.stdout.strip(), output.read_text().strip(), (bindir / "ccache").exists()

    def test_missing_cache_and_failed_install_disables_only_cache(self):
        stdout, output, _ = self.run_prepare(sudo_exit=1)
        self.assertEqual(stdout, "")
        self.assertEqual(output, "compiler_enabled=false")

    def test_successful_install_enables_cache(self):
        stdout, output, installed = self.run_prepare(sudo_exit=0)
        self.assertEqual(stdout, "")
        self.assertEqual(output, "compiler_enabled=true")
        self.assertTrue(installed)

    def test_working_preinstalled_cache_is_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            bindir = Path(temporary)
            cache = bindir / "ccache"
            cache.write_text("#!/bin/bash\necho 'ccache mock 1'\n")
            cache.chmod(0o755)
            env = os.environ.copy()
            env.pop("GITHUB_OUTPUT", None)
            output = bindir / "github-output"
            env.update({"PATH": str(bindir), "RUNNER_OS": "Linux", "CACHE_CLEAN": "false", "GITHUB_OUTPUT": str(output)})
            result = subprocess.run(["/bin/bash", str(SCRIPT)], text=True, capture_output=True, env=env, check=True)
            self.assertEqual(result.stdout.strip(), "")
            self.assertEqual(output.read_text().strip(), "compiler_enabled=true")

    def test_clean_mode_and_windows_disable_cache(self):
        self.assertEqual(self.run_prepare(clean="true", ccache=True)[1], "compiler_enabled=false")
        self.assertEqual(self.run_prepare(runner_os="Windows", ccache=True)[1], "compiler_enabled=false")

    @unittest.skipUnless(os.name == "posix" and shutil.which("timeout"), "GNU timeout is unavailable")
    def test_timeout_terminates_apt_like_child_process_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            child_pid_file = Path(temporary) / "child.pid"
            result = subprocess.run(
                [
                    shutil.which("timeout"), "--signal=TERM", "--kill-after=1s", "1s",
                    "/bin/bash", "-c", "/bin/sleep 30 & echo $! > \"$1\"; wait", "_", str(child_pid_file),
                ],
                check=False,
            )
            self.assertEqual(result.returncode, 124)
            child_pid = int(child_pid_file.read_text())
            for _ in range(20):
                if not Path(f"/proc/{child_pid}").exists():
                    break
                time.sleep(0.05)
            self.assertFalse(Path(f"/proc/{child_pid}").exists(), "timed-out command left a child process running")

    def test_action_gates_every_compiler_cache_operation_on_detected_availability(self):
        action = ACTION.read_text()
        finish = FINISH.read_text()
        self.assertIn("CCACHE_AVAILABLE: ${{ steps.ccache.outputs.compiler_enabled }}", action)
        self.assertIn("and os.environ['CCACHE_AVAILABLE'] == 'true'", action)
        self.assertIn("if: steps.keys.outputs.compiler_enabled == 'true'", action)
        self.assertIn("if: inputs.compiler_enabled == 'true'", finish)
        self.assertIn("inputs.compiler_enabled == 'true' &&", finish)


if __name__ == "__main__":
    unittest.main()
