from types import SimpleNamespace
from unittest.mock import Mock

from email_classifier_app.app import EmailClassifierApp
from email_classifier_app.database import JsonCacheRepository
from email_classifier_app.importer import EmailRecord, load_emails_from_csv
from email_classifier_app.labels import DEFAULT_TRAINING_CSV
from email_classifier_app.model import EmailClassifier, PredictionResult
from email_classifier_app.config import get_imap_account_settings


def app_with_repository(tmp_path):
    repository = JsonCacheRepository(tmp_path / "emails.json")
    repository.connect()
    app = SimpleNamespace(repository=repository, classifier=Mock(), reload_emails=Mock(), _set_status=Mock())
    app.classifier.predict.return_value = PredictionResult("Trabalho", .8, detail="Termos: formação")
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
    assert all(row["decision_detail"] == "Termos: formação" for row in reloaded.list_emails())


def test_reclassification_preserves_human_and_csv_labels(tmp_path, monkeypatch):
    app = app_with_repository(tmp_path)
    manual_id = app.repository.save_email(EmailRecord("a", "s", "b", category="Pessoal", decision_detail="Análise anterior"))
    app.repository.update_classification(manual_id, "Urgente", 1.0, source="manual")
    imported_id = app.repository.save_email(EmailRecord("b", "s", "b", category="Pessoal", category_source="imported"))
    automatic_id = app.repository.save_email(EmailRecord("c", "s", "b", category="Pessoal"))
    monkeypatch.setattr("email_classifier_app.app.messagebox.showinfo", Mock())
    EmailClassifierApp.classify_all(app)
    assert app.repository.get_email(manual_id)["category"] == "Urgente"
    assert app.repository.get_email(manual_id)["decision_detail"] == ""
    assert app.repository.get_email(imported_id)["category"] == "Pessoal"
    assert app.repository.get_email(automatic_id)["category"] == "Trabalho"
    assert app.repository.get_email(automatic_id)["decision_detail"] == "Termos: formação"
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


def test_csv_import_review_retrain_and_reopen(tmp_path, monkeypatch):
    app = app_with_repository(tmp_path)
    app.classifier = EmailClassifier(tmp_path / "model.joblib")
    info, error = Mock(), Mock()
    monkeypatch.setattr("email_classifier_app.app.messagebox.showinfo", info)
    monkeypatch.setattr("email_classifier_app.app.messagebox.showerror", error)

    seed = load_emails_from_csv(DEFAULT_TRAINING_CSV)
    assert EmailClassifierApp._save_records(app, seed) == (len(seed), 0)
    assert EmailClassifierApp._save_records(app, load_emails_from_csv(DEFAULT_TRAINING_CSV)) == (0, len(seed))
    new_csv = tmp_path / "new.csv"
    new_csv.write_text("sender,subject,body\namiga@exemplo.invalid,Passaro,codigounicotreino no quintal\n",
                       encoding="utf-8")
    assert EmailClassifierApp._save_records(app, load_emails_from_csv(new_csv)) == (1, 0)
    row = next(row for row in app.repository.list_emails() if row["subject"] == "Passaro")
    assert row["category_source"] == "automatic"
    app.selected_email = row
    app.manual_category = SimpleNamespace(get=lambda: "Pessoal")
    app.email_cache = [row]
    app.refresh_emails, app.show_details = Mock(), Mock()

    EmailClassifierApp.train_model(app)
    assert "codigounicotreino" not in app.classifier.pipeline.named_steps["tfidf"].vocabulary_
    EmailClassifierApp.save_manual_category(app)
    EmailClassifierApp.train_model(app)
    EmailClassifierApp.classify_all(app)
    error.assert_not_called()

    repository = JsonCacheRepository(app.repository.path)
    repository.connect()
    saved = repository.get_email(row["id"])
    assert (saved["category"], saved["category_source"], saved["decision_method"]) == (
        "Pessoal", "manual", "manual"
    )
    reopened = EmailClassifier(app.classifier.model_path)
    assert reopened.load()
    assert "codigounicotreino" in reopened.pipeline.named_steps["tfidf"].vocabulary_
    assert reopened.predict("Passaro", "codigounicotreino no quintal") == app.classifier.predict(
        "Passaro", "codigounicotreino no quintal"
    )
