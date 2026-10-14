#!/usr/bin/env python3
"""Enforces PROC-009 (WisewareOrg/.github PROCESS.md): the pull request title must be a
Conventional Commit; see pr-title/README.md.

Dependencies: none (stdlib only). The real work is commitlint, installed under this script's own
folder and run as a subprocess.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
COMMITLINT_BIN = SCRIPT_DIR / "node_modules" / ".bin" / "commitlint"
CONFIG_PATH = SCRIPT_DIR / ".commitlintrc-pr-title.json"


def fail(message):
    print(f"pr-title: {message}", file=sys.stderr)
    sys.exit(1)


def api_request(url, token, payload=None):
    """(status, parsed body) for a GitHub REST call; the body parses only on 200, which is the
    only status any caller reads past."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, data=payload)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, None
    except urllib.error.URLError as e:
        fail(f"cannot reach {url}: {e.reason}")


def main():
    title = os.environ.get("TITLE") or ""
    pr_number = os.environ.get("PR_NUMBER") or ""

    if not title:
        if not pr_number:
            fail("this event carries no pull request; run pr-title on pull_request")
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        token = os.environ.get("GITHUB_TOKEN", "")
        api_base = f"https://api.github.com/repos/{repo}"
        status, pull = api_request(f"{api_base}/pulls/{pr_number}", token)
        if status != 200:
            fail(f"GitHub API returned {status} for {api_base}/pulls/{pr_number}")
        title = pull.get("title") or ""

    if not title.strip():
        fail("the pull request title is empty")

    result = subprocess.run(
        [str(COMMITLINT_BIN), "--config", str(CONFIG_PATH)],
        input=title,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


if __name__ == "__main__":
    sys.exit(main())
