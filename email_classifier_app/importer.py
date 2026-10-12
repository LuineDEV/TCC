from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class EmailRecord:
    sender: str
    subject: str
    body: str
    received_at: str | None = None
    category: str | None = None
    confidence: float | None = None
    image_path: str | None = None
    ocr_text: str = ""
    capture_status: str = "Somente texto"
    ocr_status: str = "Nao executado"


def load_emails_from_csv(path: str | Path) -> list[EmailRecord]:
    frame = pd.read_csv(path)
    required = {"subject", "body"}
    missing = required.difference(frame.columns)
    if missing:
        missing_cols = ", ".join(sorted(missing))
        raise ValueError(f"O CSV precisa das colunas obrigatórias: {missing_cols}")

    records: list[EmailRecord] = []
    for _, row in frame.iterrows():
        records.append(
            EmailRecord(
                sender=str(row.get("sender", "")),
                subject=str(row.get("subject", "")),
                body=str(row.get("body", "")),
                received_at=None if pd.isna(row.get("received_at", None)) else str(row.get("received_at")),
                category=None if pd.isna(row.get("category", None)) else row.get("category"),
            )
        )
    return records
