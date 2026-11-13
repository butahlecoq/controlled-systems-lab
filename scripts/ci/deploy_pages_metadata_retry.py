"""Retry only the transient empty artifact lookup in the pinned Pages deployer."""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from typing import TextIO

EMPTY_ARTIFACT_ERROR = (
    'No artifacts named "github-pages" were found for this workflow run.'
)
DEPLOYMENT_STARTED_MARKER = "Creating Pages deployment with payload:"
MAX_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (2, 4)


def run_deployer(
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
    output: TextIO | None = None,
) -> int:
    """Run the official deploy action, retrying only its pre-deployment empty lookup."""
    stream = output if output is not None else sys.stdout

    for attempt in range(1, MAX_ATTEMPTS + 1):
        deployment_started = False
        empty_artifact_lookup = False
        process = subprocess.Popen(
            command,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        try:
            assert process.stdout is not None
            with process.stdout:
                for line in process.stdout:
                    stream.write(line)
                    stream.flush()
                    if DEPLOYMENT_STARTED_MARKER in line:
                        deployment_started = True
                    if EMPTY_ARTIFACT_ERROR in line:
                        empty_artifact_lookup = True
            result = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            process.wait()
            raise

        retryable = (
            result == 1
            and empty_artifact_lookup
            and not deployment_started
            and attempt < MAX_ATTEMPTS
        )
        if not retryable:
            return result

        time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])

    raise AssertionError("unreachable")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: deploy_pages_metadata_retry.py COMMAND [ARG ...]", file=sys.stderr)
        return 2
    return run_deployer(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
