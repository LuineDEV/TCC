import pytest

from email_classifier_app.importer import load_emails_from_csv
from email_classifier_app.model import EmailClassifier


def test_csv_missing_fields_do_not_become_nan(tmp_path):
    source = tmp_path / "emails.csv"
    source.write_text('sender,subject,body,category\n,Assunto,, Trabalho \n', encoding="utf-8")
    record = load_emails_from_csv(source)[0]
    assert (record.sender, record.body, record.category) == ("", "", "Trabalho")


def test_saved_model_learns_even_validation_only_words(tmp_path):
    records = [dict(sender="", subject=f"exclusivox{i}", body="mensagem",
                    category=("Trabalho", "Pessoal")[i % 2]) for i in range(20)]
    classifier = EmailClassifier(tmp_path / "nested" / "model.joblib")
    result = classifier.train_from_records(records)
    assert result.accuracy is not None
    loaded = EmailClassifier(classifier.model_path)
    assert loaded.load()
    vocabulary = loaded.pipeline.named_steps["tfidf"].vocabulary_
    assert all(f"exclusivox{i}" in vocabulary for i in range(20))


def test_failed_training_preserves_previous_pipeline(tmp_path):
    classifier = EmailClassifier(tmp_path / "model.joblib")
    records = [dict(subject="!!!", body="...", category=("Trabalho", "Pessoal")[i % 2])
               for i in range(6)]
    previous = object()
    classifier.pipeline = previous
    with pytest.raises(ValueError):
        classifier.train_from_records(records)
    assert classifier.pipeline is previous
