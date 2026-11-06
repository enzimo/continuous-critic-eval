"""Recognize account usage limits in Claude and Codex CLI errors.

The trial runner checks CLI error messages to identify exhausted account usage.
Review text can discuss rate limits in the code under review, so limit detection
uses the client's error output.
"""

import json
import re

# Recognize usage, session and time-window limit messages from the supported CLIs.
ACCOUNT_LIMIT = re.compile(
    r"usage limit|session limit|hit your [\w -]*limit|rate limit|quota|too many requests",
    re.I,
)
# Put in the trial runner's error message so callers can tell a limit from other failures.
LIMIT_REACHED = "account usage limit reached"


def is_account_limit(message):
    return bool(message) and ACCOUNT_LIMIT.search(message) is not None


def claude_error(stdout):
    """The error text of a failed `claude -p --output-format json` call, or ""."""
    try:
        output = json.loads(stdout)
    except ValueError:
        return ""
    if not isinstance(output, dict) or not output.get("is_error"):
        return ""
    return str(output.get("result") or "")


def codex_errors(stdout):
    """Error messages from a `codex exec --json` event stream, ignoring agent messages."""
    messages = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") not in {"error", "turn.failed"}:
            continue
        error = event.get("error") if isinstance(event.get("error"), dict) else {}
        messages.append(str(event.get("message") or error.get("message") or ""))
    return "\n".join(m for m in messages if m)
