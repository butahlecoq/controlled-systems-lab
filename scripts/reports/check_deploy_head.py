"""Allow a Pages deployment only while its run still targets current main."""

import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen


SHA = re.compile(r"[0-9a-f]{40}\Z")


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    expected = os.environ["GITHUB_SHA"]
    token = os.environ["GITHUB_TOKEN"]
    output = Path(os.environ["GITHUB_OUTPUT"])
    if not SHA.fullmatch(expected):
        raise ValueError("GITHUB_SHA must be a full Git commit ID")
    owner, name = repository.split("/")
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    url = f"{api}/repos/{quote(owner, safe='')}/{quote(name, safe='')}/branches/main"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=10) as response:
        current = json.load(response)["commit"]["sha"]
    if not isinstance(current, str) or not SHA.fullmatch(current):
        raise ValueError("GitHub returned an invalid main commit ID")
    is_current = current == expected
    with output.open("a", encoding="utf-8") as stream:
        stream.write(f"current={'true' if is_current else 'false'}\n")
    print("Deploying current main" if is_current else "Skipping stale Pages artifact")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"Cannot establish current main commit: {error}", file=sys.stderr)
        sys.exit(1)
