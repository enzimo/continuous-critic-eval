"""Explicit configuration, including Docker-secret-style file credentials."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .models import MAX_BATCH_BYTES

MIN_TOKEN_LENGTH = 8


def secret(name):
    direct, file = os.getenv(name), os.getenv(name + "_FILE")
    if direct and file:
        raise ValueError(f"Set {name} or {name}_FILE, not both")
    value = Path(file).read_text().strip() if file else (direct or "")
    if len(value) < MIN_TOKEN_LENGTH:
        raise ValueError(
            f"{name} needs at least {MIN_TOKEN_LENGTH} characters, "
            f"whether set directly or through {name}_FILE"
        )
    return value


@dataclass(frozen=True)
class Settings:
    database: Path
    admin_token: str
    ingest_token: str
    public_url: str = "http://localhost:8000"
    max_body_bytes: int = MAX_BATCH_BYTES

    def __post_init__(self):
        url = urlsplit(self.public_url)
        if url.scheme not in {"http", "https"} or not url.netloc or url.path not in {"", "/"}:
            raise ValueError("OBSERVER_PUBLIC_URL must be an http(s) origin without a path")
        if len(self.admin_token) < MIN_TOKEN_LENGTH or len(self.ingest_token) < MIN_TOKEN_LENGTH:
            raise ValueError(
                f"Both credentials must contain at least {MIN_TOKEN_LENGTH} characters"
            )
        if self.admin_token == self.ingest_token:
            raise ValueError("Operator and ingestion credentials must differ")

    @classmethod
    def from_env(cls):
        return cls(
            database=Path(os.getenv("OBSERVER_DATABASE", "/data/observer.sqlite3")),
            admin_token=secret("OBSERVER_ADMIN_TOKEN"),
            ingest_token=secret("OBSERVER_INGEST_TOKEN"),
            public_url=os.getenv("OBSERVER_PUBLIC_URL", "http://localhost:8000").rstrip("/"),
        )
