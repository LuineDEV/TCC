from __future__ import annotations

import re
import unicodedata

try:
    from nltk.corpus import stopwords
except Exception:  # pragma: no cover - only used when nltk is unavailable.
    stopwords = None


FALLBACK_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "essa",
    "esse",
    "esta",
    "este",
    "eu",
    "foi",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "que",
    "se",
    "sem",
    "um",
    "uma",
    "voce",
    "voces",
}


def _load_stopwords() -> set[str]:
    if stopwords is None:
        return FALLBACK_STOPWORDS
    try:
        return set(stopwords.words("portuguese"))
    except LookupError:
        return FALLBACK_STOPWORDS


STOPWORDS = _load_stopwords()


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def clean_text(text: str) -> str:
    text = strip_accents(str(text or "").lower())
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"\S+@\S+", " email ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [token for token in text.split() if len(token) > 2 and token not in STOPWORDS]
    return " ".join(tokens)


def combine_email_text(subject: str | None, body: str | None, ocr_text: str | None = None) -> str:
    subject = subject or ""
    body = body or ""
    ocr_text = ocr_text or ""
    return "\n".join(part for part in (subject, body, ocr_text) if part).strip()
