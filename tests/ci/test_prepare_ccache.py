import os
import subprocess
import tempfile
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
            sudo = bindir / "sudo"
            sudo.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$*\" == *'install'* ]]; then\n"
                "  if [[ \"${MOCK_SUDO_EXIT}\" == 0 ]]; then\n"
                "    cat > \"${MOCK_BINDIR}/ccache\" <<'EOF'\n"
                "#!/usr/bin/env bash\n"
                "[[ \"$1\" == --version ]] && echo 'ccache mock 1'\n"
                "EOF\n"
                "    chmod +x \"${MOCK_BINDIR}/ccache\"\n"
                "  fi\n"
                "fi\n"
                "exit \"${MOCK_SUDO_EXIT}\"\n"
            )
            sudo.chmod(0o755)
            if ccache:
                binary = bindir / "ccache"
                binary.write_text("#!/usr/bin/env bash\necho 'ccache mock 1'\n")
                binary.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "PATH": f"{bindir}:/usr/bin:/bin",
                "RUNNER_OS": runner_os,
                "CACHE_CLEAN": clean,
                "MOCK_BINDIR": str(bindir),
                "MOCK_SUDO_EXIT": str(sudo_exit),
            })
            result = subprocess.run(["bash", str(SCRIPT)], text=True, capture_output=True, env=env, check=True)
            return result.stdout.strip(), (bindir / "ccache").exists()

    def test_missing_cache_and_failed_install_disables_only_cache(self):
        enabled, _ = self.run_prepare(sudo_exit=1)
        self.assertEqual(enabled, "false")

    def test_successful_install_enables_cache(self):
        enabled, installed = self.run_prepare(sudo_exit=0)
        self.assertEqual(enabled, "true")
        self.assertTrue(installed)

    def test_working_preinstalled_cache_is_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            bindir = Path(temporary)
            cache = bindir / "ccache"
            cache.write_text("#!/usr/bin/env bash\necho 'ccache mock 1'\n")
            cache.chmod(0o755)
            env = os.environ.copy()
            env.update({"PATH": f"{bindir}:/usr/bin:/bin", "RUNNER_OS": "Linux", "CACHE_CLEAN": "false"})
            result = subprocess.run(["bash", str(SCRIPT)], text=True, capture_output=True, env=env, check=True)
            self.assertEqual(result.stdout.strip(), "true")

    def test_clean_mode_and_windows_disable_cache(self):
        self.assertEqual(self.run_prepare(clean="true", ccache=True)[0], "false")
        self.assertEqual(self.run_prepare(runner_os="Windows", ccache=True)[0], "false")

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
