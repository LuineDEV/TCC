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
    source_key: str | None = None
    category_source: str = "automatic"
    decision_method: str = "unknown"
    decision_detail: str = ""


def load_emails_from_csv(path: str | Path) -> list[EmailRecord]:
    frame = pd.read_csv(path, keep_default_na=False)
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
                received_at=str(row.get("received_at", "")).strip() or None,
                category=str(row.get("category", "")).strip() or None,
                category_source="imported" if str(row.get("category", "")).strip() else "automatic",
                decision_method="imported" if str(row.get("category", "")).strip() else "unknown",
            )
        )
    return records
