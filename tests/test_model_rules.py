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
    assert "verifique imediatamente" in result.detail


def test_urgent_phrase_is_normalized_before_matching(tmp_path: Path):
    result = classifier(tmp_path)._predict_with_rules(
        "equipe@exemplo.invalid", "Servidor fora do ar", "Equipe avisada.", ""
    )
    assert result is not None and result.category == "Urgente"


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


def test_logistic_explanation_uses_terms_supported_by_the_actual_prediction(tmp_path):
    model = classifier(tmp_path)
    model.train_from_records([
        {"subject": term, "body": f"{term} exemplo {index}", "category": category}
        for term, category in (("xilogravura", "Pessoal"), ("filologia", "Trabalho"), ("hidraulica", "Urgente"))
        for index in range(3)
    ])
    result = model.predict("Xilogravura", "Prática de xilogravura")
    assert result.category == "Pessoal"
    assert result.source == "model"
    assert "xilogravura" in result.detail
    assert "hidraulica" not in result.detail


def test_binary_logistic_explanation_works_for_both_classes(tmp_path):
    model = classifier(tmp_path)
    model.train_from_records([
        {"subject": term, "body": term, "category": category}
        for term, category in (("xilogravura", "Pessoal"), ("filologia", "Trabalho"))
        for _ in range(3)
    ])
    assert "xilogravura" in model.predict("xilogravura", "").detail
    assert "filologia" in model.predict("filologia", "").detail
