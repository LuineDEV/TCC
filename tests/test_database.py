from email_classifier_app.database import JsonCacheRepository
from email_classifier_app.importer import EmailRecord
import pytest
from pathlib import Path
from email_classifier_app.database import MySQLRepository


def test_json_repository_updates_imported_email_content(tmp_path):
    repository = JsonCacheRepository(path=tmp_path / "emails.json")
    repository.connect()
    email_id = repository.save_email(EmailRecord("", "Nenhum selecionado", "texto bruto"))

    repository.update_email_content(
        email_id,
        sender="jobalerts-noreply@linkedin.com",
        subject="Vaga de estagio",
        body="Descricao da vaga",
    )

    saved = repository.get_email(email_id)
    assert saved["sender"] == "jobalerts-noreply@linkedin.com"
    assert saved["subject"] == "Vaga de estagio"
    assert saved["body"] == "Descricao da vaga"


def test_failed_cache_replace_preserves_existing_file(tmp_path, monkeypatch):
    repository = JsonCacheRepository(path=tmp_path / "emails.json")
    repository.connect()
    original = repository.path.read_bytes()

    def fail_replace(*args):
        raise OSError("replacement failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        repository.save_email(EmailRecord("a@email.com", "Assunto", "Corpo"))
    assert repository.path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [repository.path]


def test_json_repository_clears_only_email_records(tmp_path):
    repository = JsonCacheRepository(path=tmp_path / "emails.json")
    repository.connect()
    repository.save_email(EmailRecord("a@email.com", "Primeiro", "Conteudo"))
    repository.save_email(EmailRecord("b@email.com", "Segundo", "Conteudo"))
    repository.log("INFO", "modelo treinado")

    removed = repository.clear_emails()

    assert removed == 2
    assert repository.list_emails() == []
    assert len(repository.data["logs"]) == 1


def test_json_repository_persists_visual_capture_fields(tmp_path):
    repository = JsonCacheRepository(path=tmp_path / "emails.json")
    repository.connect()

    email_id = repository.save_email(
        EmailRecord(
            "loja@email.com",
            "Oferta na imagem",
            "Conteudo copiado",
            image_path=str(tmp_path / "email.png"),
            ocr_text="Desconto de cinquenta por cento",
            capture_status="Completa",
            ocr_status="Concluido",
        )
    )

    saved = repository.get_email(email_id)
    assert saved["image_path"].endswith("email.png")
    assert saved["ocr_text"] == "Desconto de cinquenta por cento"
    assert saved["capture_status"] == "Completa"
    assert saved["ocr_status"] == "Concluido"


def test_clear_emails_removes_capture_file_but_preserves_model_and_logs(tmp_path):
    captures = tmp_path / "email_images"
    captures.mkdir()
    capture = captures / "message.png"
    capture.write_bytes(b"image")
    repository = JsonCacheRepository(path=tmp_path / "emails.json", capture_dir=captures)
    repository.connect()
    repository.save_email(EmailRecord("a@email.com", "Assunto", "Corpo", image_path=str(capture)))
    repository.log("INFO", "modelo treinado")

    repository.clear_emails()

    assert not capture.exists()
    assert len(repository.data["logs"]) == 1


def test_search_scans_full_body_before_paging_and_counts(tmp_path):
    repository = JsonCacheRepository(path=tmp_path / "emails.json")
    repository.connect()
    repository.save_email(EmailRecord("one@example.com", "Primeiro", "x" * 300 + " target-marker", category="Trabalho"))
    repository.save_email(EmailRecord("two@example.com", "Segundo", "outro texto", category="Pessoal"))
    repository.save_email(EmailRecord("three@example.com", "Terceiro", "target-marker", category="Trabalho"))

    assert repository.count_email_summaries("target-marker") == 2
    assert [row["subject"] for row in repository.search_email_summaries("target-marker", limit=1)] == ["Terceiro"]
    assert [row["subject"] for row in repository.search_email_summaries("target-marker", category="Trabalho", offset=1)] == ["Primeiro"]
    assert repository.search_email_summaries("target-marker", category="Pessoal") == []


def test_json_persists_decision_method_and_defaults_legacy_records(tmp_path):
    path = tmp_path / "emails.json"
    repository = JsonCacheRepository(path=path)
    repository.connect()
    email_id = repository.save_email(EmailRecord("a@example.com", "Assunto", "Corpo"))
    repository.update_classification(email_id, "Trabalho", 0.9, source="manual", decision_method="manual")
    assert repository.get_email(email_id)["decision_method"] == "manual"
    assert repository.list_email_summaries()[0]["decision_method"] == "manual"

    path.write_text('{"emails": [{"id": 9, "sender": "old", "subject": "legacy", "body": "full"}], "logs": []}', encoding="utf-8")
    legacy = JsonCacheRepository(path=path)
    legacy.connect()
    assert legacy.get_email(9)["decision_method"] == "unknown"
    assert legacy.list_email_summaries()[0]["decision_method"] == "unknown"


def test_json_source_key_lookup(tmp_path):
    repository = JsonCacheRepository(path=tmp_path / "emails.json")
    repository.connect()
    repository.save_email(EmailRecord("a@example.com", "Assunto", "Corpo", source_key="imap:uidvalidity:42"))
    assert repository.source_key_exists("imap:uidvalidity:42")
    assert not repository.source_key_exists("imap:uidvalidity:43")
    assert not repository.source_key_exists("")


def test_mysql_schema_migrates_decision_method_for_existing_database():
    class Cursor:
        def __init__(self):
            self.statements = []

        def execute(self, sql, params=None):
            self.statements.append(sql)

        def fetchall(self):
            if self.statements[-1] == "SHOW INDEX FROM emails":
                return []
            return [("id",), ("category",)]

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            pass

    repository = MySQLRepository()
    repository.connection = Connection()
    repository.initialize_schema()

    assert any("ADD COLUMN decision_method VARCHAR(20) DEFAULT 'unknown'" in sql
               for sql in repository.connection.cursor_instance.statements)
