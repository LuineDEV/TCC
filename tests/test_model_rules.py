from pathlib import Path

from email_classifier_app.model import EmailClassifier, build_feature_text


def classifier(tmp_path: Path) -> EmailClassifier:
    return EmailClassifier(model_path=tmp_path / "model.joblib")


def test_linkedin_job_alert_is_classified_as_work(tmp_path: Path):
    result = classifier(tmp_path).predict(
        "Fullstack Python Engineer - Work from home",
        "Novas vagas correspondem as suas preferencias.",
        sender="jobalerts-noreply@linkedin.com",
    )

    assert result.category == "Trabalho"
    assert result.confidence >= 0.90


def test_real_security_deadline_is_classified_as_urgent(tmp_path: Path):
    result = classifier(tmp_path).predict(
        "Tentativa de login",
        "Detectamos um acesso incomum. Verifique imediatamente.",
        sender="seguranca@banco.com",
    )

    assert result.category == "Urgente"


def test_last_minute_marketing_message_is_not_treated_as_urgent(tmp_path: Path):
    result = classifier(tmp_path).predict(
        "Esta precisando enviar um item de ultima hora?",
        "Conheca o servico de entregas da Uber.",
        sender="uber@uber.com",
    )

    assert result.category == "Pessoal"


def test_feature_text_prioritizes_sender_and_subject_and_limits_noisy_ocr():
    text = build_feature_text("rh@empresa.com", "Vaga Python", "corpo", "x" * 9000)

    assert text.count("Vaga Python") >= 2
    assert "rh@empresa.com" in text
    assert len(text) < 7000
