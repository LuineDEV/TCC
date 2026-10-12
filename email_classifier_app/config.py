from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"
CACHE_DIR = BASE_DIR / "cache"
GMAIL_PROFILE_DIR = CACHE_DIR / "gmail_browser_profile"
EMAIL_IMAGE_DIR = CACHE_DIR / "email_images"


def load_env_file(path: Path | None = None) -> None:
    env_path = path or BASE_DIR / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    user: str
    password: str
    database: str


def get_database_settings() -> DatabaseSettings:
    load_env_file()
    return DatabaseSettings(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "email_classifier_tcc"),
    )


def ensure_directories() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    MODEL_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)
    GMAIL_PROFILE_DIR.mkdir(exist_ok=True)
    EMAIL_IMAGE_DIR.mkdir(exist_ok=True)
