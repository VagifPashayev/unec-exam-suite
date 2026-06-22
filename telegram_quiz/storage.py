"""Transactional persistence for users, roles, quiz metadata, and audit events."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


VALID_LANGUAGES = {"ru", "en", "az"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class QuizFile:
    id: int
    filename: str
    title: str
    sha256: str
    question_count: int
    uploaded_by: int | None
    created_at: str
    active: bool


class BotStorage:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def initialize(
        self,
        owner_id: int,
        *,
        approved_file: Path | None = None,
        pending_file: Path | None = None,
        languages_file: Path | None = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    language TEXT CHECK(language IN ('ru', 'en', 'az')),
                    status TEXT NOT NULL DEFAULT 'new'
                        CHECK(status IN ('new', 'pending', 'approved', 'blocked')),
                    role TEXT NOT NULL DEFAULT 'user'
                        CHECK(role IN ('user', 'admin', 'owner')),
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quiz_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    question_count INTEGER NOT NULL CHECK(question_count > 0),
                    uploaded_by INTEGER,
                    created_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1))
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """INSERT INTO users(user_id, status, role, updated_at)
                   VALUES (?, 'approved', 'owner', ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       status = 'approved', role = 'owner', updated_at = excluded.updated_at""",
                (owner_id, _now()),
            )
            migrated = connection.execute(
                "SELECT 1 FROM audit_log WHERE action = 'legacy_json_migrated' LIMIT 1"
            ).fetchone()
            if not migrated:
                self._migrate_json(
                    connection,
                    owner_id,
                    approved_file=approved_file,
                    pending_file=pending_file,
                    languages_file=languages_file,
                )
                connection.execute(
                    "INSERT INTO audit_log(actor_id, action, target, created_at) VALUES (?, ?, ?, ?)",
                    (owner_id, "legacy_json_migrated", None, _now()),
                )

    @staticmethod
    def _read_json(path: Path | None, default):
        if path is None:
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return default

    def _migrate_json(
        self,
        connection: sqlite3.Connection,
        owner_id: int,
        *,
        approved_file: Path | None,
        pending_file: Path | None,
        languages_file: Path | None,
    ) -> None:
        languages = self._read_json(languages_file, {})
        approved = {int(value) for value in self._read_json(approved_file, [])}
        pending = {int(value) for value in self._read_json(pending_file, [])}
        all_ids = approved | pending | {int(key) for key in languages}
        for user_id in all_ids:
            if user_id == owner_id:
                continue
            language = languages.get(str(user_id))
            if language not in VALID_LANGUAGES:
                language = None
            status = "approved" if user_id in approved else "pending"
            connection.execute(
                """INSERT INTO users(user_id, language, status, role, updated_at)
                   VALUES (?, ?, ?, 'user', ?)
                   ON CONFLICT(user_id) DO NOTHING""",
                (user_id, language, status, _now()),
            )

    def upsert_identity(
        self, user_id: int, username: str | None, first_name: str | None
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO users(user_id, username, first_name, status, role, updated_at)
                   VALUES (?, ?, ?, 'new', 'user', ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       username = excluded.username,
                       first_name = excluded.first_name,
                       updated_at = excluded.updated_at""",
                (user_id, username, first_name, _now()),
            )

    def get_language(self, user_id: int, default: str = "en") -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT language FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return (
            row["language"] if row and row["language"] in VALID_LANGUAGES else default
        )

    def has_language(self, user_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT language FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return bool(row and row["language"] in VALID_LANGUAGES)

    def set_language(self, user_id: int, language: str) -> None:
        if language not in VALID_LANGUAGES:
            raise ValueError("unsupported language")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO users(user_id, language, status, role, updated_at)
                   VALUES (?, ?, 'new', 'user', ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       language = excluded.language, updated_at = excluded.updated_at""",
                (user_id, language, _now()),
            )

    def status(self, user_id: int) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row["status"] if row else None

    def role(self, user_id: int) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row["role"] if row else None

    def is_approved(self, user_id: int) -> bool:
        return self.status(user_id) == "approved"

    def is_admin(self, user_id: int) -> bool:
        return self.role(user_id) in {"admin", "owner"} and self.is_approved(user_id)

    def is_owner(self, user_id: int) -> bool:
        return self.role(user_id) == "owner"

    def request_access(self, user_id: int) -> bool:
        """Set a new user to pending. Return True only for a new request."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row and row["status"] != "new":
                return False
            if row:
                connection.execute(
                    "UPDATE users SET status = 'pending', updated_at = ? WHERE user_id = ?",
                    (_now(), user_id),
                )
            else:
                connection.execute(
                    "INSERT INTO users(user_id, status, role, updated_at) VALUES (?, 'pending', 'user', ?)",
                    (user_id, _now()),
                )
            return True

    def set_access(self, actor_id: int, user_id: int, approved: bool) -> bool:
        status = "approved" if approved else "blocked"
        with self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row and row["role"] == "owner":
                return False
            connection.execute(
                """INSERT INTO users(user_id, status, role, updated_at)
                   VALUES (?, ?, 'user', ?)
                   ON CONFLICT(user_id) DO UPDATE SET status = excluded.status,
                       updated_at = excluded.updated_at""",
                (user_id, status, _now()),
            )
            self._audit(
                connection,
                actor_id,
                "access_approved" if approved else "access_blocked",
                str(user_id),
            )
            return True

    def grant_admin(self, actor_id: int, user_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row and row["role"] == "owner":
                return False
            connection.execute(
                """INSERT INTO users(user_id, status, role, updated_at)
                   VALUES (?, 'approved', 'admin', ?)
                   ON CONFLICT(user_id) DO UPDATE SET status = 'approved', role = 'admin',
                       updated_at = excluded.updated_at""",
                (user_id, _now()),
            )
            self._audit(connection, actor_id, "admin_granted", str(user_id))
            return True

    def revoke_admin(self, actor_id: int, user_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row or row["role"] != "admin":
                return False
            connection.execute(
                "UPDATE users SET role = 'user', updated_at = ? WHERE user_id = ?",
                (_now(), user_id),
            )
            self._audit(connection, actor_id, "admin_revoked", str(user_id))
            return True

    def list_users(self, *, status: str | None = None) -> list[sqlite3.Row]:
        query = (
            "SELECT user_id, username, first_name, language, status, role FROM users"
        )
        params: tuple = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY role DESC, user_id"
        with self._connect() as connection:
            return list(connection.execute(query, params).fetchall())

    def admin_ids(self) -> list[int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id FROM users WHERE role IN ('owner', 'admin') AND status = 'approved'"
            ).fetchall()
        return [row["user_id"] for row in rows]

    def list_audit(self, limit: int = 30) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return list(
                connection.execute(
                    "SELECT actor_id, action, target, created_at FROM audit_log ORDER BY id DESC LIMIT ?",
                    (max(1, min(limit, 100)),),
                ).fetchall()
            )

    def register_quiz(
        self,
        *,
        filename: str,
        title: str,
        sha256: str,
        question_count: int,
        uploaded_by: int | None,
    ) -> QuizFile:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO quiz_files(filename, title, sha256, question_count, uploaded_by, created_at, active)
                   VALUES (?, ?, ?, ?, ?, ?, 1)
                   ON CONFLICT(filename) DO UPDATE SET title = excluded.title,
                       sha256 = excluded.sha256, question_count = excluded.question_count,
                       uploaded_by = excluded.uploaded_by, created_at = excluded.created_at,
                       active = 1""",
                (filename, title, sha256, question_count, uploaded_by, _now()),
            )
            row = connection.execute(
                "SELECT * FROM quiz_files WHERE filename = ?", (filename,)
            ).fetchone()
            if uploaded_by:
                self._audit(connection, uploaded_by, "quiz_uploaded", filename)
        return self._quiz_from_row(row)

    def list_quizzes(self, *, active_only: bool = True) -> list[QuizFile]:
        query = "SELECT * FROM quiz_files"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY title COLLATE NOCASE"
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [self._quiz_from_row(row) for row in rows]

    def get_quiz(self, quiz_id: int, *, active_only: bool = True) -> QuizFile | None:
        query = "SELECT * FROM quiz_files WHERE id = ?"
        if active_only:
            query += " AND active = 1"
        with self._connect() as connection:
            row = connection.execute(query, (quiz_id,)).fetchone()
        return self._quiz_from_row(row) if row else None

    def deactivate_quiz(self, actor_id: int, quiz_id: int) -> QuizFile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM quiz_files WHERE id = ? AND active = 1", (quiz_id,)
            ).fetchone()
            if not row:
                return None
            connection.execute(
                "UPDATE quiz_files SET active = 0 WHERE id = ?", (quiz_id,)
            )
            self._audit(connection, actor_id, "quiz_deleted", row["filename"])
        return self._quiz_from_row(row)

    @staticmethod
    def _quiz_from_row(row: sqlite3.Row) -> QuizFile:
        return QuizFile(
            id=row["id"],
            filename=row["filename"],
            title=row["title"],
            sha256=row["sha256"],
            question_count=row["question_count"],
            uploaded_by=row["uploaded_by"],
            created_at=row["created_at"],
            active=bool(row["active"]),
        )

    @staticmethod
    def _audit(
        connection: sqlite3.Connection, actor_id: int, action: str, target: str | None
    ) -> None:
        connection.execute(
            "INSERT INTO audit_log(actor_id, action, target, created_at) VALUES (?, ?, ?, ?)",
            (actor_id, action, target, _now()),
        )
