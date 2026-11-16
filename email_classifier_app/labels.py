"""Small classification labels imported without the scientific Python stack."""

from pathlib import Path

from .config import DATA_DIR, MODEL_DIR

CATEGORIES = ("Urgente", "Trabalho", "Pessoal")
DEFAULT_MODEL_PATH = MODEL_DIR / "email_classifier.joblib"
DEFAULT_TRAINING_CSV = DATA_DIR / "sample_emails.csv"
