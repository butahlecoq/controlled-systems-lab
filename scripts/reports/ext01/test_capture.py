"""Regression: large child output and failed attempts must be durably captured."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


source = Path(__file__).with_name("collect_ext01.py")
spec = importlib.util.spec_from_file_location("ext01_collect_under_test", source)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory() as directory:
    module.OUT = Path(directory)
    large = "import sys; sys.stdout.buffer.write(b'x'*1048576)"
    captured = module.run_monitored("large", command_override=[sys.executable, "-c", large])
    assert len(captured["stdout"]) == 1048576
    assert (module.OUT / "large.stdout.jsonl").read_bytes() == b"x" * 1048576
    assert (module.OUT / "large.stderr.txt").read_bytes() == b""
    assert json.loads((module.OUT / "large.process.json").read_text())["return_code"] == 0

    failing = "import sys; sys.stdout.buffer.write(b'y'*1048576); sys.stderr.write('deliberate failure'); sys.exit(9)"
    try:
        module.run_monitored("failed", command_override=[sys.executable, "-c", failing])
    except ValueError as error:
        assert "raw stdout/stderr retained" in str(error)
    else:
        raise AssertionError("failed child was accepted")
    assert (module.OUT / "failed.stdout.jsonl").read_bytes() == b"y" * 1048576
    assert (module.OUT / "failed.stderr.txt").read_text() == "deliberate failure"
    status = json.loads((module.OUT / "failed.process.json").read_text())
    assert status["return_code"] == 9
    assert status["stdout_sha256"] == module.sha(b"y" * 1048576)

print("large stdout and failed-child evidence preserved")
