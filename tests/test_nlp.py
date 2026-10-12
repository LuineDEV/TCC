from email_classifier_app.nlp import combine_email_text


def test_combined_email_text_includes_ocr_without_replacing_original_body():
    text = combine_email_text("Assunto", "Corpo normal", "Texto encontrado na imagem")

    assert text == "Assunto\nCorpo normal\nTexto encontrado na imagem"
