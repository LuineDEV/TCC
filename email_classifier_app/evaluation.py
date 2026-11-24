"""Offline evaluation with fixed data partitions and no access to the mailbox."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy
import scipy
import sklearn
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.naive_bayes import MultinomialNB

from .labels import CATEGORIES
from .model import EmailClassifier, build_feature_text, build_text_pipeline
from .nlp import STOPWORDS, clean_text


PARTITIONS = ("treino", "validacao", "revisao", "teste")
REQUIRED = {"id", "grupo", "particao", "sender", "subject", "body", "category"}


@dataclass(frozen=True)
class Example:
    id: str
    group: str
    sender: str
    subject: str
    body: str
    category: str

    @property
    def text(self) -> str:
        return build_feature_text(self.sender, self.subject, self.body, "")


def read_partitions(data: bytes) -> dict[str, list[Example]]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if not REQUIRED.issubset(reader.fieldnames or ()):
        raise ValueError("Campos obrigatorios: " + ", ".join(sorted(REQUIRED)))
    partitions = {name: [] for name in PARTITIONS}
    ids: set[str] = set()
    ownership: dict[str, str] = {}
    contents: dict[str, str] = {}

    for row in reader:
        fields = {key: (row[key] or "").strip() for key in REQUIRED}
        identifier, group, partition = (fields[key] for key in ("id", "grupo", "particao"))
        category = fields["category"]
        if not identifier or not group or partition not in partitions or category not in CATEGORIES:
            raise ValueError(f"Linha {reader.line_num}: ID, grupo, particao ou categoria invalida.")
        if identifier in ids:
            raise ValueError(f"ID repetido: {identifier}.")
        if ownership.setdefault(group, partition) != partition:
            raise ValueError(f"Grupo {group} presente em mais de uma particao.")
        example = Example(identifier, group, fields["sender"], fields["subject"], fields["body"], category)
        normalized = clean_text(f"{example.subject} {example.body}")
        if not normalized:
            raise ValueError(f"Mensagem {identifier} sem texto utilizavel.")
        if normalized in contents:
            raise ValueError(f"Texto duplicado: {contents[normalized]} e {identifier}.")
        contents[normalized] = identifier
        ids.add(identifier)
        partitions[partition].append(example)

    for name, examples in partitions.items():
        if {row.category for row in examples} != set(CATEGORIES):
            raise ValueError(f"A particao {name} precisa conter todas as categorias.")
    return partitions


def measure(rows: list[Example], predicted: list[str], sources: list[str]) -> dict:
    expected = [row.category for row in rows]
    report = classification_report(
        expected, predicted, labels=CATEGORIES, output_dict=True, zero_division=0
    )
    return {
        "accuracy": accuracy_score(expected, predicted),
        "f1_macro": report["macro avg"]["f1-score"],
        "classes": {label: report[label] for label in CATEGORIES},
        "confusion_matrix": confusion_matrix(expected, predicted, labels=CATEGORIES).tolist(),
        "predictions": [
            {"id": row.id, "expected": row.category, "predicted": category, "source": source}
            for row, category, source in zip(rows, predicted, sources, strict=True)
        ],
    }


def experiment_fingerprint() -> dict:
    package = Path(__file__).resolve().parent
    files = ("evaluation.py", "labels.py", "model.py", "nlp.py")
    return {
        "python": ".".join(str(value) for value in sys.version_info[:3]),
        "sklearn": sklearn.__version__,
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "code": {
            name: hashlib.sha256((package / name).read_text(encoding="utf-8").encode()).hexdigest()
            for name in files
        },
        "stopwords": hashlib.sha256("\n".join(sorted(STOPWORDS)).encode()).hexdigest(),
        "protocol": hashlib.sha256(
            (package.parent / "docs" / "protocolo_experimental.md").read_text(encoding="utf-8").encode()
        ).hexdigest(),
    }


def validate_review_log(data: bytes, examples: list[Example]) -> dict:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    required = {"id", "reviewer", "category_before", "category_confirmed", "justification"}
    if not required.issubset(reader.fieldnames or ()):
        raise ValueError("Campos do registro de revisao: " + ", ".join(sorted(required)))
    remaining = {example.id: example.category for example in examples}
    changed = 0
    for row in reader:
        fields = {key: (row[key] or "").strip() for key in required}
        identifier = fields["id"]
        if identifier not in remaining:
            raise ValueError(f"Registro de revisao: ID fora do lote ou repetido (linha {reader.line_num}).")
        if (not fields["reviewer"] or not fields["justification"]
                or fields["category_before"] not in CATEGORIES
                or fields["category_confirmed"] != remaining.pop(identifier)):
            raise ValueError(f"Registro de revisao inconsistente (linha {reader.line_num}).")
        changed += fields["category_before"] != fields["category_confirmed"]
    if remaining:
        raise ValueError("Ha mensagens no lote de revisao sem registro correspondente.")
    return {"confirmed": len(examples), "changed": changed, "sha256": hashlib.sha256(data).hexdigest()}


def evaluate(data: bytes, review_log: bytes | None = None) -> dict:
    parts = read_partitions(data)
    initial, validation, review, test = (parts[name] for name in PARTITIONS)
    review_evidence = validate_review_log(review_log, review) if review_log is not None else None
    reports: dict[str, dict] = {}
    validations: dict[str, dict] = {}
    rule_predictions = [
        EmailClassifier._predict_with_rules(row.sender, row.subject, row.body, "")
        for row in test
    ]
    sources = ["rule" if result else "model" for result in rule_predictions]

    for stage, training in (("antes", initial), ("depois", initial + review)):
        training_texts = [row.text for row in training]
        training_labels = [row.category for row in training]
        for algorithm, pipeline in (
            ("logistica", build_text_pipeline()),
            ("naive_bayes", build_text_pipeline(MultinomialNB())),
        ):
            key = f"{algorithm}_{stage}"
            pipeline.fit(training_texts, training_labels)
            validation_pred = pipeline.predict([row.text for row in validation]).tolist()
            validations[key] = measure(validation, validation_pred, ["model"] * len(validation))
            predicted = pipeline.predict([row.text for row in test]).tolist()
            reports[key] = measure(test, predicted, ["model"] * len(test))
            if algorithm == "logistica":
                hybrid = [
                    result.category if result else category
                    for result, category in zip(rule_predictions, predicted, strict=True)
                ]
                reports[f"hibrido_{stage}"] = measure(test, hybrid, sources)

    covered = sum(result is not None for result in rule_predictions)
    rule_correct = sum(
        result is not None and result.category == row.category
        for result, row in zip(rule_predictions, test, strict=True)
    )
    return {
        "dataset_sha256": hashlib.sha256(data).hexdigest(),
        "sklearn_version": sklearn.__version__,
        "stopwords_sha256": hashlib.sha256("\n".join(sorted(STOPWORDS)).encode()).hexdigest(),
        "fingerprint": experiment_fingerprint(),
        "review_log": review_evidence,
        "labels": list(CATEGORIES),
        "partitions": {
            name: {
                "ids": [row.id for row in rows],
                "counts": dict(Counter(row.category for row in rows)),
            }
            for name, rows in parts.items()
        },
        "rules": {"covered": covered, "correct": rule_correct, "total": len(test)},
        "validation": validations,
        "test": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, nargs="?")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze", action="store_true", help="Grava a assinatura da implementacao.")
    parser.add_argument("--lock", type=Path, help="Assinatura gravada antes de abrir a base de teste.")
    parser.add_argument("--review-log", type=Path, help="Registro do lote revisado por uma pessoa.")
    args = parser.parse_args()
    if args.freeze:
        if args.dataset or args.lock or args.review_log:
            parser.error("--freeze deve ser usado sem base de dados ou registro de revisao.")
    elif args.dataset is None or bool(args.lock) != bool(args.review_log):
        parser.error("Informe o CSV. Para a rodada confirmatoria, use --lock e --review-log juntos.")
    inputs = (args.dataset, args.lock, args.review_log)
    if any(path is not None and path.resolve() == args.output.resolve() for path in inputs):
        parser.error("O arquivo de saida deve ser diferente dos arquivos de entrada.")
    try:
        if args.freeze:
            report = experiment_fingerprint()
        else:
            review_log = None
            if args.lock:
                locked = json.loads(args.lock.read_text(encoding="utf-8"))
                if locked != experiment_fingerprint():
                    raise ValueError("O codigo ou o ambiente difere da assinatura congelada.")
                review_log = args.review_log.read_bytes()
            report = evaluate(args.dataset.read_bytes(), review_log)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Falha na avaliacao: {exc}\n")
    if args.freeze:
        print("Assinatura gravada.")
        return
    for scenario, result in report["test"].items():
        print(f"{scenario:20} accuracy={result['accuracy']:.3f} f1_macro={result['f1_macro']:.3f}")


if __name__ == "__main__":
    main()
