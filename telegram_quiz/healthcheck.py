"""Container healthcheck that verifies both the process and Telegram token."""

from __future__ import annotations

import json
import os
import urllib.request


def main() -> int:
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        return 1
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/getMe",
        headers={"User-Agent": "unec-exam-bot-healthcheck"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.load(response)
        return 0 if payload.get("ok") else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
