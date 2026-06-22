"""Container healthcheck for Telegram connectivity and persistent state."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import urllib.request
from pathlib import Path


def main() -> int:
    token = os.environ.get("BOT_TOKEN", "")
    data_dir = Path(os.environ.get("DATA_DIR", "/app/data"))
    if not token:
        return 1
    try:
        with sqlite3.connect(data_dir / "bot.db", timeout=3) as connection:
            connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".health-", delete=True):
            pass
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getMe",
            headers={"User-Agent": "unec-exam-bot-healthcheck"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.load(response)
        return 0 if payload.get("ok") else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
