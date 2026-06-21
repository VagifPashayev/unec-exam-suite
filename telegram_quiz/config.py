"""Configuration and small persistent stores for the Telegram bot."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data")).resolve()
QUIZ_DIR = Path(os.environ.get("QUIZ_DIR", BASE_DIR / "quizzes")).resolve()

APPROVED_USERS_FILE = DATA_DIR / "approved_users.json"
PENDING_USERS_FILE = DATA_DIR / "pending_users.json"
USER_LANGUAGES_FILE = DATA_DIR / "user_languages.json"


def _load_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return default


def _save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


APPROVED_USERS = {int(value) for value in _load_json(APPROVED_USERS_FILE, [])}
PENDING_USERS = {int(value) for value in _load_json(PENDING_USERS_FILE, [])}
USER_LANGUAGES = {
    int(key): value
    for key, value in _load_json(USER_LANGUAGES_FILE, {}).items()
    if value in {"ru", "en", "az"}
}

if ADMIN_ID:
    APPROVED_USERS.add(ADMIN_ID)


def save_approved_users() -> None:
    _save_json(APPROVED_USERS_FILE, sorted(APPROVED_USERS))


def save_pending_users() -> None:
    _save_json(PENDING_USERS_FILE, sorted(PENDING_USERS))


def save_user_languages() -> None:
    _save_json(
        USER_LANGUAGES_FILE,
        {str(key): value for key, value in sorted(USER_LANGUAGES.items())},
    )


def validate_config() -> None:
    missing = []
    if not TOKEN:
        missing.append("BOT_TOKEN")
    if ADMIN_ID <= 0:
        missing.append("ADMIN_ID")
    if missing:
        raise RuntimeError(f"Missing or invalid configuration: {', '.join(missing)}")
    QUIZ_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
