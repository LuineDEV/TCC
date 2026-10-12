from email_classifier_app.reader_presenter import build_extracted_text, capture_summary, format_received_at


def test_extracted_text_keeps_email_and_ocr_in_separate_sections():
    text = build_extracted_text("Mensagem normal", "Texto dentro da arte")

    assert text == "TEXTO DO E-MAIL\nMensagem normal\n\nTEXTO ENCONTRADO NAS IMAGENS\nTexto dentro da arte"


def test_capture_summary_explains_partial_capture_and_ocr_state():
    summary = capture_summary("Parcial", "Indisponivel", has_image=True)

    assert summary == "Captura parcial | OCR indisponivel"


def test_format_received_at_keeps_only_readable_date_and_time():
    assert format_received_at("2026-09-06T19:58:22") == "06/09/2026 19:58"
