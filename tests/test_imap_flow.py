from types import SimpleNamespace
from unittest.mock import Mock

from email_classifier_app.app import EmailClassifierApp
from email_classifier_app.database import JsonCacheRepository
from email_classifier_app.importer import EmailRecord
from email_classifier_app.model import PredictionResult
from email_classifier_app.config import get_imap_account_settings


def app_with_repository(tmp_path):
    repository = JsonCacheRepository(tmp_path / "emails.json")
    repository.connect()
    app = SimpleNamespace(repository=repository, classifier=Mock(), reload_emails=Mock(), _set_status=Mock())
    app.classifier.predict.return_value = PredictionResult("Trabalho", .8)
    app._record_key = EmailClassifierApp._record_key
    return app


def test_imap_identity_deduplicates_reimports_but_preserves_identical_distinct_messages(tmp_path):
    app = app_with_repository(tmp_path)
    records = [EmailRecord("a@example.com", "Assunto", "Corpo", source_key="imap:" + char * 64)
               for char in ("a", "b")]
    assert EmailClassifierApp._save_records(app, records) == (2, 0)
    assert EmailClassifierApp._save_records(app, records) == (0, 2)
    reloaded = JsonCacheRepository(app.repository.path)
    reloaded.connect()
    assert len(reloaded.list_emails()) == 2
    assert all(row["source_key"] and row["category_source"] == "automatic" for row in reloaded.list_emails())


def test_reclassification_preserves_human_and_csv_labels(tmp_path, monkeypatch):
    app = app_with_repository(tmp_path)
    manual_id = app.repository.save_email(EmailRecord("a", "s", "b", category="Pessoal"))
    app.repository.update_classification(manual_id, "Urgente", 1.0, source="manual")
    imported_id = app.repository.save_email(EmailRecord("b", "s", "b", category="Pessoal", category_source="imported"))
    automatic_id = app.repository.save_email(EmailRecord("c", "s", "b", category="Pessoal"))
    monkeypatch.setattr("email_classifier_app.app.messagebox.showinfo", Mock())
    EmailClassifierApp.classify_all(app)
    assert app.repository.get_email(manual_id)["category"] == "Urgente"
    assert app.repository.get_email(imported_id)["category"] == "Pessoal"
    assert app.repository.get_email(automatic_id)["category"] == "Trabalho"
    assert app.classifier.predict.call_count == 1


def test_training_excludes_automatic_and_legacy_labels(tmp_path, monkeypatch):
    app = app_with_repository(tmp_path)
    for index in range(6):
        app.repository.save_email(EmailRecord("a", str(index), "b", category=("Urgente", "Pessoal")[index % 2],
                                              category_source="manual"))
    for source in ("automatic", "legacy"):
        app.repository.save_email(EmailRecord("a", source, "b", category="Trabalho", category_source=source))
    app.classifier.train_from_records.return_value = SimpleNamespace(accuracy=None, trained_rows=6, model_path="model")
    monkeypatch.setattr("email_classifier_app.app.messagebox.showinfo", Mock())
    EmailClassifierApp.train_model(app)
    used = app.classifier.train_from_records.call_args.args[0]
    assert len(used) == 6
    assert all(row["category_source"] == "manual" for row in used)


def test_imap_account_settings_are_loaded_from_private_env_file(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("IMAP_HOST=imap.uni5.net\nIMAP_PORT=993\n"
                        "IMAP_USERNAME=contato@example.com\nIMAP_PASSWORD=segredo-local\n"
                        "IMAP_FOLDER=INBOX\nIMAP_LIMIT=35\n", encoding="utf-8")
    monkeypatch.delenv("IMAP_PASSWORD", raising=False)
    settings = get_imap_account_settings(env_path)
    assert (settings.host, settings.port, settings.username, settings.password,
            settings.folder, settings.limit) == (
                "imap.uni5.net", 993, "contato@example.com", "segredo-local", "INBOX", 35)
