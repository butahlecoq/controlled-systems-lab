#!/usr/bin/env python3
"""Check that perf capability requires decoded sample records."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from obs04_perf_probe import count_cycles_samples  # noqa: E402

assert count_cycles_samples("# Samples: 0\n# header mentions cycles\n") == 0
assert count_cycles_samples("\nworker 12/12 [001] 1.2: cycles:u: 123 cycles\n") == 1
assert count_cycles_samples(
    "worker 12/12 [001] 1.2: cycles:u: 123 cycles\n"
    "# lost events: 0\n"
    "worker 12/12 [001] 1.3: cycles:u: 123 cycles\n"
) == 2
print("perf sample validation tests passed")
