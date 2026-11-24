from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from .config import ensure_directories
from .nlp import clean_text, strip_accents
from .labels import CATEGORIES, DEFAULT_MODEL_PATH, DEFAULT_TRAINING_CSV


MODEL_VERSION = 2

URGENT_PATTERNS = (
    "verifique imediatamente",
    "acao imediata",
    "prazo final",
    "vence hoje",
    "vencimento hoje",
    "tentativa de login",
    "acesso incomum",
    "compra suspeita",
    "conta bloqueada",
    "servidor fora do ar",
    "incidente de seguranca",
    "resultado critico",
    "evacuacao preventiva",
    "vazamento",
)
NORMALIZED_URGENT_PATTERNS = tuple(clean_text(pattern) for pattern in URGENT_PATTERNS)
WORK_SENDER_PATTERNS = ("jobalerts", "job-alert", "jobs-noreply", "infojobs", "vagas.com", "gupy")
WORK_TERMS = (
    "vaga", "estagio", "desenvolvedor", "developer", "engineer", "reuniao",
    "relatorio", "contrato", "projeto", "sprint", "cliente", "fornecedor",
    "curriculo", "entrevista", "processo seletivo", "trabalho", "equipe",
    "orcamento", "faculdade", "orientacao tcc",
)
PERSONAL_SENDER_PATTERNS = ("amazon.", "aliexpress.", "tiktok.", "uber.", "shein.", "shopee.")


def _compact_source(text: str | None, limit: int) -> str:
    ignored = ("caixa de entrada", "cancelar inscricao", "responder", "encaminhar")
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in str(text or "").splitlines():
        line = " ".join(raw_line.split())
        normalized = clean_text(line)
        if not line or not normalized or any(term in normalized for term in ignored):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        lines.append(line)
    return "\n".join(lines)[:limit]


def build_feature_text(sender: str, subject: str, body: str, ocr_text: str) -> str:
    subject = " ".join(str(subject or "").split())
    sender = " ".join(str(sender or "").split())
    body = _compact_source(body, 2400)
    ocr_text = _compact_source(ocr_text, 3200)
    return "\n".join(
        part for part in (sender, sender, subject, subject, subject, body, ocr_text) if part
    )


def build_text_pipeline(classifier=None) -> Pipeline:
    return Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    preprocessor=clean_text,
                    lowercase=False,
                    ngram_range=(1, 2),
                    min_df=1,
                ),
            ),
            (
                "classifier",
                classifier if classifier is not None else LogisticRegression(
                    max_iter=1000, class_weight="balanced"
                ),
            ),
        ]
    )


@dataclass
class PredictionResult:
    category: str
    confidence: float
    source: str = "model"
    detail: str = ""


@dataclass
class TrainingResult:
    accuracy: float | None
    report: str
    model_path: Path
    trained_rows: int


class EmailClassifier:
    def __init__(self, model_path: Path = DEFAULT_MODEL_PATH) -> None:
        ensure_directories()
        self.model_path = model_path
        self.pipeline: Pipeline | None = None

    @property
    def is_ready(self) -> bool:
        return self.pipeline is not None

    def load(self) -> bool:
        if not self.model_path.exists():
            return False
        payload = joblib.load(self.model_path)
        if not isinstance(payload, dict) or payload.get("version") != MODEL_VERSION:
            self.pipeline = None
            return False
        self.pipeline = payload.get("pipeline")
        return self.pipeline is not None

    def train_from_csv(self, csv_path: Path = DEFAULT_TRAINING_CSV) -> TrainingResult:
        frame = pd.read_csv(csv_path)
        required = {"subject", "body", "category"}
        missing = required.difference(frame.columns)
        if missing:
            missing_cols = ", ".join(sorted(missing))
            raise ValueError(f"O CSV de treino precisa das colunas: {missing_cols}")

        return self._train_frame(frame)

    def train_from_records(self, records: list[dict[str, Any]]) -> TrainingResult:
        frame = pd.DataFrame.from_records(records)
        required = {"subject", "body", "category"}
        missing = required.difference(frame.columns)
        if missing:
            missing_cols = ", ".join(sorted(missing))
            raise ValueError(f"A base local precisa dos campos: {missing_cols}")

        return self._train_frame(frame)

    def _train_frame(self, frame: pd.DataFrame) -> TrainingResult:
        frame = frame.dropna(subset=["subject", "body", "category"]).copy()
        frame["category"] = frame["category"].astype(str).str.strip()
        frame = frame[frame["category"].isin(CATEGORIES)]
        if "ocr_text" not in frame.columns:
            frame["ocr_text"] = ""
        if "sender" not in frame.columns:
            frame["sender"] = ""
        frame["ocr_text"] = frame["ocr_text"].fillna("")
        frame["sender"] = frame["sender"].fillna("")
        frame["text"] = frame.apply(
            lambda row: build_feature_text(row["sender"], row["subject"], row["body"], row["ocr_text"]), axis=1
        )
        frame = frame[frame["text"].str.strip() != ""]

        if len(frame) < 6:
            raise ValueError("São necessários pelo menos 6 e-mails categorizados para treinar o modelo.")
        if frame["category"].nunique() < 2:
            raise ValueError("A base de treino precisa ter pelo menos 2 categorias diferentes.")

        category_counts = frame["category"].value_counts()
        pipeline = build_text_pipeline()

        can_validate = len(frame) >= 10 and category_counts.min() >= 2
        if can_validate:
            x_train, x_test, y_train, y_test = train_test_split(
                frame["text"],
                frame["category"],
                test_size=0.30,
                random_state=42,
                stratify=frame["category"],
            )
            pipeline.fit(x_train, y_train)
            predictions = pipeline.predict(x_test)
            accuracy: float | None = accuracy_score(y_test, predictions)
            report = classification_report(y_test, predictions, zero_division=0)
        else:
            accuracy = None
            report = "Base pequena ou desbalanceada; validação separada não realizada."

        # Evaluate on held-out data first, then learn all reviewed examples.
        # Keep the working model untouched if fitting or persistence fails.
        pipeline.fit(frame["text"], frame["category"])
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.model_path.parent) as directory:
            temporary_model = Path(directory) / self.model_path.name
            joblib.dump({"version": MODEL_VERSION, "pipeline": pipeline}, temporary_model)
            temporary_model.replace(self.model_path)
        self.pipeline = pipeline
        return TrainingResult(
            accuracy=accuracy,
            report=report,
            model_path=self.model_path,
            trained_rows=len(frame),
        )

    def ensure_model(self) -> None:
        if self.load():
            return
        if DEFAULT_TRAINING_CSV.exists():
            self.train_from_csv(DEFAULT_TRAINING_CSV)
            return
        raise FileNotFoundError("Nenhum modelo treinado ou CSV de treino foi encontrado.")

    def predict(self, subject: str, body: str, ocr_text: str = "", sender: str = "") -> PredictionResult:
        rule_result = self._predict_with_rules(sender, subject, body, ocr_text)
        if rule_result is not None:
            return rule_result
        if self.pipeline is None:
            self.ensure_model()

        pipeline = self.pipeline
        assert pipeline is not None
        text = build_feature_text(sender, subject, body, ocr_text)
        vectorizer = pipeline.named_steps["tfidf"]
        classifier = pipeline.named_steps["classifier"]
        vector = vectorizer.transform([text])
        probabilities = classifier.predict_proba(vector)[0]
        predicted = int(probabilities.argmax())
        runner_up = max((i for i in range(len(probabilities)) if i != predicted), key=probabilities.__getitem__)
        if len(probabilities) == 2 and classifier.coef_.shape[0] == 1:
            weights = classifier.coef_[0] * (1 if predicted == 1 else -1)
        else:
            weights = classifier.coef_[predicted] - classifier.coef_[runner_up]
        contributions = vector.data * weights[vector.indices]
        names = vectorizer.get_feature_names_out()
        strongest = [
            str(names[vector.indices[i]])
            for i in sorted(range(len(contributions)), key=contributions.__getitem__, reverse=True)
            if contributions[i] > 0 and len(names[vector.indices[i]]) <= 48
        ][:3]
        detail = "Termos que favoreceram a previsão: " + ", ".join(strongest) if strongest else ""
        return PredictionResult(str(classifier.classes_[predicted]), float(probabilities[predicted]), detail=detail)

    @staticmethod
    def _predict_with_rules(sender: str, subject: str, body: str, ocr_text: str) -> PredictionResult | None:
        sender_text = strip_accents(str(sender or "").lower())
        content = clean_text(f"{subject}\n{body[:2000]}\n{ocr_text[:2000]}")
        for pattern, normalized in zip(URGENT_PATTERNS, NORMALIZED_URGENT_PATTERNS, strict=True):
            if normalized in content:
                return PredictionResult("Urgente", 0.96, "rule", f"Expressão de urgência: “{pattern}”.")
        if "urgente" in content:
            for term in ("hoje", "prazo", "bloqueio", "seguranca"):
                if term in content:
                    return PredictionResult("Urgente", 0.91, "rule", f"“urgente” junto de “{term}”.")
        if any(pattern in sender_text for pattern in WORK_SENDER_PATTERNS):
            return PredictionResult("Trabalho", 0.96, "rule", "Padrão de remetente associado a vagas.")
        work_matches = [term for term in WORK_TERMS if term in content]
        work_score = len(work_matches)
        if work_score >= 2:
            return PredictionResult(
                "Trabalho", min(0.94, 0.82 + work_score * 0.03), "rule",
                "Vocabulário profissional: " + ", ".join(work_matches[:3]),
            )
        if any(pattern in sender_text for pattern in PERSONAL_SENDER_PATTERNS):
            return PredictionResult("Pessoal", 0.90, "rule", "Padrão de remetente associado a consumo ou lazer.")
        return None
