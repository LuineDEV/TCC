from email_classifier_app.database import JsonCacheRepository
from email_classifier_app.importer import EmailRecord


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
