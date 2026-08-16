from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .config import APP_VERSION, CONTENT_VERSION, SCHEMA_VERSION, ensure_app_directories


class RestoreError(ValueError):
    """Raised when an exported progress file cannot be safely restored."""


@dataclass(frozen=True)
class RestorePreview:
    schema_version: int
    content_version: str
    app_version: str
    exported_at: str
    progress_records: int
    quiz_attempts: int
    settings: int


def _validate_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a timezone offset")
    return value


def _validate_json_text(value: str, *, require_object: bool) -> str:
    if len(value.encode("utf-8")) > 1_048_576:
        raise ValueError("JSON value exceeds the 1 MiB row limit")
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("must contain valid JSON text") from exc
    if require_object and not isinstance(parsed, dict):
        raise ValueError("must contain a JSON object")
    return value


class RestoreRow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProgressRestoreRow(RestoreRow):
    item_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]*$")
    item_type: Literal[
        "activity", "code_lab", "knowledge_check", "lesson", "orientation", "project", "quiz"
    ]
    status: Literal["completed"]
    content_version: str
    updated_at: str
    payload_json: str

    @field_validator("content_version")
    @classmethod
    def validate_content_version(cls, value: str) -> str:
        if value != CONTENT_VERSION:
            raise ValueError("does not match the export content version")
        return value

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: str) -> str:
        return _validate_timestamp(value)

    @field_validator("payload_json")
    @classmethod
    def validate_payload(cls, value: str) -> str:
        return _validate_json_text(value, require_object=True)


class QuizAttemptRestoreRow(RestoreRow):
    id: int = Field(gt=0)
    quiz_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]*$")
    score: float = Field(ge=0, le=1)
    answers_json: str
    content_version: str
    created_at: str

    @field_validator("content_version")
    @classmethod
    def validate_content_version(cls, value: str) -> str:
        if value != CONTENT_VERSION:
            raise ValueError("does not match the export content version")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        return _validate_timestamp(value)

    @field_validator("answers_json")
    @classmethod
    def validate_answers(cls, value: str) -> str:
        return _validate_json_text(value, require_object=True)


class SettingRestoreRow(RestoreRow):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    value_json: str
    updated_at: str

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: str) -> str:
        return _validate_timestamp(value)

    @field_validator("value_json")
    @classmethod
    def validate_value(cls, value: str) -> str:
        return _validate_json_text(value, require_object=False)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _validate_row_collection(
    rows: list[Any], model: type[RestoreRow], collection: str, unique_field: str
) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for index, row in enumerate(rows):
        try:
            record = model.model_validate(row)
        except ValidationError as exc:
            detail = exc.errors(include_url=False)[0]
            location = ".".join(str(part) for part in detail["loc"])
            raise RestoreError(
                f"The {collection} row {index + 1} is invalid at {location}: {detail['msg']}."
            ) from exc
        dumped = record.model_dump()
        identity = dumped[unique_field]
        if identity in seen:
            raise RestoreError(
                f"The {collection} rows contain duplicate {unique_field}: {identity!r}."
            )
        seen.add(identity)
        validated.append(dumped)
    return validated


class ProgressStore:
    def __init__(self, db_path: Path | None = None, backup_dir: Path | None = None) -> None:
        paths = ensure_app_directories()
        self.db_path = db_path or paths["state"] / "progress.db"
        self.backup_dir = backup_dir or paths["backups"]
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS progress (
                    item_id TEXT PRIMARY KEY,
                    item_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content_version TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS quiz_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quiz_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    answers_json TEXT NOT NULL,
                    content_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.executemany(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                [
                    ("schema_version", str(SCHEMA_VERSION)),
                    ("content_version", CONTENT_VERSION),
                    ("app_version", APP_VERSION),
                ],
            )

    def mark_completed(
        self, item_id: str, item_type: str, payload: dict[str, Any] | None = None
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO progress(item_id, item_type, status, content_version, updated_at, payload_json)
                VALUES (?, ?, 'completed', ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    item_type=excluded.item_type,
                    status='completed',
                    content_version=excluded.content_version,
                    updated_at=excluded.updated_at,
                    payload_json=excluded.payload_json
                """,
                (
                    item_id,
                    item_type,
                    CONTENT_VERSION,
                    _utc_now(),
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )

    def is_completed(self, item_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM progress WHERE item_id = ?", (item_id,)
            ).fetchone()
        return bool(row and row["status"] == "completed")

    def completed_ids(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT item_id FROM progress WHERE status = 'completed'"
            ).fetchall()
        return {row["item_id"] for row in rows}

    def status_summary(self, required_ids: list[str]) -> dict[str, int | bool]:
        completed = self.completed_ids()
        count = len(set(required_ids) & completed)
        return {
            "completed": count,
            "total": len(required_ids),
            "is_complete": count == len(required_ids),
        }

    def set_setting(self, key: str, value: Any) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=excluded.updated_at
                """,
                (key, json.dumps(value, ensure_ascii=False), _utc_now()),
            )

    def export_bytes(self) -> bytes:
        with self._connect() as connection:
            progress = [dict(row) for row in connection.execute("SELECT * FROM progress")]
            attempts = [dict(row) for row in connection.execute("SELECT * FROM quiz_attempts")]
            settings = [dict(row) for row in connection.execute("SELECT * FROM settings")]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "content_version": CONTENT_VERSION,
            "app_version": APP_VERSION,
            "exported_at": _utc_now(),
            "progress": progress,
            "quiz_attempts": attempts,
            "settings": settings,
        }
        digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
        envelope = {
            **payload,
            "integrity": {"algorithm": "sha256", "digest": digest},
        }
        return json.dumps(envelope, indent=2, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _parse_export(data: bytes | str) -> dict[str, Any]:
        try:
            decoded = data.decode("utf-8") if isinstance(data, bytes) else data
            envelope = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RestoreError("The selected file is not valid UTF-8 progress JSON.") from exc
        if not isinstance(envelope, dict):
            raise RestoreError("The progress export must be a top-level JSON object.")
        required = {
            "schema_version",
            "content_version",
            "app_version",
            "exported_at",
            "progress",
            "quiz_attempts",
            "settings",
            "integrity",
        }
        missing = required - set(envelope)
        if missing:
            raise RestoreError(f"The progress export is missing: {', '.join(sorted(missing))}.")
        unexpected = set(envelope) - required
        if unexpected:
            raise RestoreError(
                f"The progress export has unsupported fields: {', '.join(sorted(unexpected))}."
            )
        integrity = envelope["integrity"]
        if not isinstance(integrity, dict) or set(integrity) != {"algorithm", "digest"}:
            raise RestoreError("The progress export integrity record is malformed.")
        if integrity.get("algorithm") != "sha256":
            raise RestoreError("The progress export uses an unsupported integrity algorithm.")
        digest_value = integrity.get("digest")
        if (
            not isinstance(digest_value, str)
            or len(digest_value) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in digest_value)
        ):
            raise RestoreError("The progress export integrity digest is malformed.")
        payload = {key: value for key, value in envelope.items() if key != "integrity"}
        digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
        if digest != integrity.get("digest"):
            raise RestoreError("The progress export failed its integrity check.")
        if type(envelope["schema_version"]) is not int:
            raise RestoreError("The progress export schema version is malformed.")
        if envelope["schema_version"] != SCHEMA_VERSION:
            direction = "newer" if envelope["schema_version"] > SCHEMA_VERSION else "older"
            raise RestoreError(f"This {direction} schema is not supported by Milestone 1.")
        if not isinstance(envelope["content_version"], str):
            raise RestoreError("The progress export content version is malformed.")
        if envelope["content_version"] != CONTENT_VERSION:
            raise RestoreError("The progress export belongs to an incompatible content version.")
        if not isinstance(envelope["app_version"], str) or not envelope["app_version"].strip():
            raise RestoreError("The progress export app version is malformed.")
        try:
            _validate_timestamp(envelope["exported_at"])
        except ValueError as exc:
            raise RestoreError(f"The progress export timestamp {exc}.") from exc
        for collection in ("progress", "quiz_attempts", "settings"):
            if not isinstance(envelope[collection], list):
                raise RestoreError(f"The {collection} records are malformed.")
        envelope["progress"] = _validate_row_collection(
            envelope["progress"], ProgressRestoreRow, "progress", "item_id"
        )
        envelope["quiz_attempts"] = _validate_row_collection(
            envelope["quiz_attempts"], QuizAttemptRestoreRow, "quiz_attempts", "id"
        )
        envelope["settings"] = _validate_row_collection(
            envelope["settings"], SettingRestoreRow, "settings", "key"
        )
        return envelope

    def preview_restore(self, data: bytes | str) -> RestorePreview:
        envelope = self._parse_export(data)
        return RestorePreview(
            schema_version=envelope["schema_version"],
            content_version=envelope["content_version"],
            app_version=envelope["app_version"],
            exported_at=envelope["exported_at"],
            progress_records=len(envelope["progress"]),
            quiz_attempts=len(envelope["quiz_attempts"]),
            settings=len(envelope["settings"]),
        )

    def _create_backup(self) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.backup_dir / f"progress-before-restore-{timestamp}.db"
        with self._connect() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        return target

    def restore(self, data: bytes | str) -> Path:
        envelope = self._parse_export(data)
        backup = self._create_backup()
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM progress")
                connection.execute("DELETE FROM quiz_attempts")
                connection.execute("DELETE FROM settings")
                for row in envelope["progress"]:
                    connection.execute(
                        """
                        INSERT INTO progress(item_id, item_type, status, content_version, updated_at, payload_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["item_id"],
                            row["item_type"],
                            row["status"],
                            row["content_version"],
                            row["updated_at"],
                            row["payload_json"],
                        ),
                    )
                for row in envelope["quiz_attempts"]:
                    connection.execute(
                        """
                        INSERT INTO quiz_attempts(id, quiz_id, score, answers_json, content_version, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["id"],
                            row["quiz_id"],
                            row["score"],
                            row["answers_json"],
                            row["content_version"],
                            row["created_at"],
                        ),
                    )
                for row in envelope["settings"]:
                    connection.execute(
                        "INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)",
                        (row["key"], row["value_json"], row["updated_at"]),
                    )
                connection.commit()
            except Exception as exc:
                connection.rollback()
                raise RestoreError("Restore failed; the current profile was left unchanged.") from exc
        return backup

    def reset(self) -> None:
        self._create_backup()
        with self._connect() as connection:
            connection.execute("DELETE FROM progress")
            connection.execute("DELETE FROM quiz_attempts")
            connection.execute("DELETE FROM settings")
