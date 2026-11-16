from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import mysql.connector
from mysql.connector import Error

from .config import CACHE_DIR, EMAIL_IMAGE_DIR, DatabaseSettings, ensure_directories, get_database_settings
from .importer import EmailRecord


class MySQLRepository:
    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self.settings = settings or get_database_settings()
        self.connection: mysql.connector.MySQLConnection | None = None

    def connect(self) -> None:
        self.connection = mysql.connector.connect(
            host=self.settings.host,
            port=self.settings.port,
            user=self.settings.user,
            password=self.settings.password,
            connection_timeout=1,
        )
        cursor = self.connection.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{self.settings.database}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.close()
        self.connection.database = self.settings.database
        self.initialize_schema()

    def initialize_schema(self) -> None:
        assert self.connection is not None
        cursor = self.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS emails (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sender VARCHAR(255),
                subject TEXT NOT NULL,
                body LONGTEXT NOT NULL,
                received_at VARCHAR(40),
                category VARCHAR(60),
                confidence DECIMAL(6, 5),
                image_path TEXT,
                ocr_text LONGTEXT,
                capture_status VARCHAR(40) DEFAULT 'Somente texto',
                ocr_status VARCHAR(40) DEFAULT 'Nao executado',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.execute("SHOW COLUMNS FROM emails")
        columns = {str(row[0]) for row in cursor.fetchall()}
        migrations = {
            "source_key": "ALTER TABLE emails ADD COLUMN source_key VARCHAR(80)",
            "category_source": "ALTER TABLE emails ADD COLUMN category_source VARCHAR(20) DEFAULT 'legacy'",
            "decision_method": "ALTER TABLE emails ADD COLUMN decision_method VARCHAR(20) DEFAULT 'unknown'",
            "image_path": "ALTER TABLE emails ADD COLUMN image_path TEXT",
            "ocr_text": "ALTER TABLE emails ADD COLUMN ocr_text LONGTEXT",
            "capture_status": "ALTER TABLE emails ADD COLUMN capture_status VARCHAR(40) DEFAULT 'Somente texto'",
            "ocr_status": "ALTER TABLE emails ADD COLUMN ocr_status VARCHAR(40) DEFAULT 'Nao executado'",
        }
        for column, statement in migrations.items():
            if column not in columns:
                cursor.execute(statement)
        cursor.execute("SHOW INDEX FROM emails")
        index_names = {str(row[2]) for row in cursor.fetchall()}
        if "idx_emails_source_key" not in index_names:
            cursor.execute("CREATE INDEX idx_emails_source_key ON emails (source_key)")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                level VARCHAR(20) NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        self.connection.commit()
        cursor.close()

    def save_email(self, record: EmailRecord) -> int:
        assert self.connection is not None
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO emails (
                sender, subject, body, received_at, category, confidence,
                image_path, ocr_text, capture_status, ocr_status, source_key, category_source, decision_method
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.sender,
                record.subject,
                record.body,
                record.received_at,
                record.category,
                record.confidence,
                record.image_path,
                record.ocr_text,
                record.capture_status,
                record.ocr_status,
                record.source_key,
                record.category_source,
                getattr(record, "decision_method", "unknown"),
            ),
        )
        self.connection.commit()
        inserted_id = int(cursor.lastrowid)
        cursor.close()
        return inserted_id

    def list_emails(self, category: str | None = None) -> list[dict[str, Any]]:
        assert self.connection is not None
        cursor = self.connection.cursor(dictionary=True)
        if category and category != "Todas":
            cursor.execute("SELECT * FROM emails WHERE category = %s ORDER BY id DESC", (category,))
        else:
            cursor.execute("SELECT * FROM emails ORDER BY id DESC")
        rows = list(cursor.fetchall())
        cursor.close()
        return rows

    def list_email_summaries(self) -> list[dict[str, Any]]:
        assert self.connection is not None
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                id,
                sender,
                subject,
                LEFT(body, 220) AS body,
                received_at,
                category,
                confidence,
                image_path,
                LEFT(ocr_text, 220) AS ocr_text,
                capture_status,
                ocr_status,
                source_key,
                category_source,
                decision_method,
                created_at,
                updated_at
            FROM emails
            ORDER BY id DESC
            """
        )
        rows = list(cursor.fetchall())
        cursor.close()
        return rows

    def search_email_summaries(
        self, query: str = "", category: str | None = None, limit: int = 80, offset: int = 0
    ) -> list[dict[str, Any]]:
        assert self.connection is not None
        limit, offset = _page_args(limit, offset)
        cursor = self.connection.cursor(dictionary=True)
        clauses: list[str] = []
        values: list[Any] = []
        if category and category != "Todas":
            clauses.append("category = %s")
            values.append(category)
        if query.strip():
            pattern = f"%{query.strip()}%"
            clauses.append("(sender LIKE %s OR subject LIKE %s OR body LIKE %s OR ocr_text LIKE %s)")
            values.extend([pattern] * 4)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cursor.execute(
            f"SELECT id, sender, subject, LEFT(body, 220) AS body, received_at, category, confidence, "
            f"image_path, LEFT(ocr_text, 220) AS ocr_text, capture_status, ocr_status, source_key, "
            f"category_source, decision_method, created_at, updated_at FROM emails {where} "
            "ORDER BY id DESC LIMIT %s OFFSET %s",
            (*values, limit, offset),
        )
        rows = list(cursor.fetchall())
        cursor.close()
        return rows

    def source_key_exists(self, key: str) -> bool:
        if not key:
            return False
        assert self.connection is not None
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1 FROM emails WHERE source_key = %s LIMIT 1", (key,))
        exists = cursor.fetchone() is not None
        cursor.close()
        return exists

    def count_email_summaries(self, query: str = "", category: str | None = None) -> int:
        assert self.connection is not None
        clauses: list[str] = []
        values: list[Any] = []
        if category and category != "Todas":
            clauses.append("category = %s")
            values.append(category)
        if query.strip():
            pattern = f"%{query.strip()}%"
            clauses.append("(sender LIKE %s OR subject LIKE %s OR body LIKE %s OR ocr_text LIKE %s)")
            values.extend([pattern] * 4)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cursor = self.connection.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM emails {where}", tuple(values))
        count = int(cursor.fetchone()[0])
        cursor.close()
        return count

    def get_email(self, email_id: int) -> dict[str, Any] | None:
        assert self.connection is not None
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM emails WHERE id = %s", (email_id,))
        row = cursor.fetchone()
        cursor.close()
        return row

    def update_classification(self, email_id: int, category: str, confidence: float, source: str = "automatic", decision_method: str = "unknown") -> None:
        assert self.connection is not None
        cursor = self.connection.cursor()
        cursor.execute(
            "UPDATE emails SET category = %s, confidence = %s, category_source = %s, decision_method = %s WHERE id = %s",
            (category, confidence, source, decision_method, email_id),
        )
        self.connection.commit()
        cursor.close()

    def update_email_content(self, email_id: int, sender: str, subject: str, body: str) -> None:
        assert self.connection is not None
        cursor = self.connection.cursor()
        cursor.execute(
            "UPDATE emails SET sender = %s, subject = %s, body = %s WHERE id = %s",
            (sender, subject, body, email_id),
        )
        self.connection.commit()
        cursor.close()

    def clear_emails(self) -> int:
        assert self.connection is not None
        cursor = self.connection.cursor()
        cursor.execute("SELECT image_path FROM emails WHERE image_path IS NOT NULL")
        paths = [str(row[0]) for row in cursor.fetchall() if row[0]]
        cursor.execute("DELETE FROM emails")
        removed = cursor.rowcount
        self.connection.commit()
        cursor.close()
        _remove_capture_files(paths, EMAIL_IMAGE_DIR)
        return int(removed)

    def log(self, level: str, message: str) -> None:
        assert self.connection is not None
        cursor = self.connection.cursor()
        cursor.execute("INSERT INTO app_logs (level, message) VALUES (%s, %s)", (level, message))
        self.connection.commit()
        cursor.close()


class JsonCacheRepository:
    """Fallback local para demonstração quando o MySQL ainda não estiver configurado."""

    def __init__(self, path: Path | None = None, capture_dir: Path | None = None) -> None:
        ensure_directories()
        self.path = path or CACHE_DIR / "emails_cache.json"
        self.capture_dir = capture_dir or EMAIL_IMAGE_DIR
        self.data: dict[str, list[dict[str, Any]]] = {"emails": [], "logs": []}
        self._lock = threading.RLock()

    def connect(self) -> None:
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            self.data.setdefault("emails", [])
            self.data.setdefault("logs", [])
            for email in self.data["emails"]:
                email.setdefault("source_key", None)
                email.setdefault("category_source", "legacy")
                email.setdefault("decision_method", "unknown")
                email.setdefault("image_path", None)
                email.setdefault("ocr_text", "")
                email.setdefault("capture_status", "Somente texto")
                email.setdefault("ocr_status", "Nao executado")
        else:
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             delete=False) as stream:
                temporary_path = Path(stream.name)
                json.dump(self.data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def save_email(self, record: EmailRecord) -> int:
        with self._lock:
            next_id = 1 + max((int(item["id"]) for item in self.data["emails"]), default=0)
            payload = asdict(record)
            payload.setdefault("decision_method", "unknown")
            payload["id"] = next_id
            payload["created_at"] = datetime.now().isoformat(timespec="seconds")
            payload["updated_at"] = payload["created_at"]
            self.data["emails"].append(payload)
            self._save()
            return next_id

    def list_emails(self, category: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            emails = [dict(email) for email in self.data["emails"]]
        if category and category != "Todas":
            emails = [email for email in emails if email.get("category") == category]
        return sorted(emails, key=lambda item: int(item["id"]), reverse=True)

    def list_email_summaries(self) -> list[dict[str, Any]]:
        with self._lock:
            snapshot = [dict(email) for email in self.data["emails"]]
        emails = [_to_summary(email) for email in snapshot]
        return sorted(emails, key=lambda item: int(item["id"]), reverse=True)

    def search_email_summaries(
        self, query: str = "", category: str | None = None, limit: int = 80, offset: int = 0
    ) -> list[dict[str, Any]]:
        limit, offset = _page_args(limit, offset)
        needle = query.strip().casefold()
        emails = self.list_emails(category)
        if needle:
            emails = [email for email in emails if needle in " ".join(str(email.get(field) or "") for field in ("sender", "subject", "body", "ocr_text")).casefold()]
        return [_to_summary(email) for email in emails[offset:offset + limit]]

    def source_key_exists(self, key: str) -> bool:
        if not key:
            return False
        with self._lock:
            return any(email.get("source_key") == key for email in self.data["emails"])

    def count_email_summaries(self, query: str = "", category: str | None = None) -> int:
        needle = query.strip().casefold()
        emails = self.list_emails(category)
        if needle:
            emails = [email for email in emails if needle in " ".join(str(email.get(field) or "") for field in ("sender", "subject", "body", "ocr_text")).casefold()]
        return len(emails)

    def get_email(self, email_id: int) -> dict[str, Any] | None:
        with self._lock:
            for email in self.data["emails"]:
                if int(email["id"]) == int(email_id):
                    return dict(email)
        return None

    def update_classification(self, email_id: int, category: str, confidence: float, source: str = "automatic", decision_method: str = "unknown") -> None:
        with self._lock:
            for email in self.data["emails"]:
                if int(email["id"]) == int(email_id):
                    email["category"] = category
                    email["confidence"] = confidence
                    email["category_source"] = source
                    email["decision_method"] = decision_method
                    email["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    break
            self._save()

    def update_email_content(self, email_id: int, sender: str, subject: str, body: str) -> None:
        with self._lock:
            for email in self.data["emails"]:
                if int(email["id"]) == int(email_id):
                    email["sender"] = sender
                    email["subject"] = subject
                    email["body"] = body
                    email["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    break
            self._save()

    def clear_emails(self) -> int:
        with self._lock:
            removed = len(self.data["emails"])
            paths = [str(email["image_path"]) for email in self.data["emails"] if email.get("image_path")]
            self.data["emails"] = []
            self._save()
        _remove_capture_files(paths, self.capture_dir)
        return removed

    def log(self, level: str, message: str) -> None:
        with self._lock:
            self.data["logs"].append(
                {"level": level, "message": message, "created_at": datetime.now().isoformat(timespec="seconds")}
            )
            self._save()


def _remove_capture_files(paths: list[str], capture_dir: Path) -> None:
    root = capture_dir.resolve()
    for value in paths:
        try:
            path = Path(value).resolve()
            if path.parent == root and path.is_file():
                path.unlink()
        except (OSError, RuntimeError):
            continue


def _to_summary(email: dict[str, Any]) -> dict[str, Any]:
    summary = dict(email)
    summary["body"] = str(summary.get("body", ""))[:220]
    summary.setdefault("decision_method", "unknown")
    return summary


def _page_args(limit: int, offset: int) -> tuple[int, int]:
    return max(0, int(limit)), max(0, int(offset))


def create_repository() -> tuple[MySQLRepository | JsonCacheRepository, str]:
    repository = MySQLRepository()
    try:
        repository.connect()
        return repository, "MySQL local conectado"
    except Error:
        fallback = JsonCacheRepository()
        fallback.connect()
        return fallback, "Modo demonstração: MySQL indisponível, usando cache JSON local"
