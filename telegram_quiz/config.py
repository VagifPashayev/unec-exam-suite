"""Configuration and persistent service initialization for the Telegram bot."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from file_service import initialize_quiz_files
from storage import BotStorage


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data")).resolve()
QUIZ_DIR = Path(os.environ.get("QUIZ_DIR", DATA_DIR / "quizzes")).resolve()
BUNDLED_QUIZ_DIR = BASE_DIR / "quizzes"
TRASH_DIR = DATA_DIR / "trash"

APPROVED_USERS_FILE = DATA_DIR / "approved_users.json"
PENDING_USERS_FILE = DATA_DIR / "pending_users.json"
USER_LANGUAGES_FILE = DATA_DIR / "user_languages.json"
STORAGE = BotStorage(DATA_DIR / "bot.db")


def validate_config() -> None:
    missing = []
    if not TOKEN:
        missing.append("BOT_TOKEN")
    if ADMIN_ID <= 0:
        missing.append("ADMIN_ID")
    if missing:
        raise RuntimeError(f"Missing or invalid configuration: {', '.join(missing)}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE.initialize(
        ADMIN_ID,
        approved_file=APPROVED_USERS_FILE,
        pending_file=PENDING_USERS_FILE,
        languages_file=USER_LANGUAGES_FILE,
    )
    initialize_quiz_files(STORAGE, BUNDLED_QUIZ_DIR, QUIZ_DIR)
