from email_classifier_app.gmail_rpa import GmailInboxImporter, GmailMessage


def test_importer_limits_collected_messages_to_requested_amount():
    collected_limits: list[int] = []

    def collect_messages(limit: int) -> list[GmailMessage]:
        collected_limits.append(limit)
        return [
            GmailMessage("a@empresa.com", "Contrato", "Revisar o contrato", "Hoje"),
            GmailMessage("b@empresa.com", "Reuniao", "Confirmar horario", "Hoje"),
            GmailMessage("c@empresa.com", "Evento", "Convite para evento", "Hoje"),
        ]

    importer = GmailInboxImporter(max_messages=2, collector=collect_messages)

    messages = importer.import_inbox()

    assert collected_limits == [2]
    assert [message.subject for message in messages] == ["Contrato", "Reuniao"]


def test_gmail_message_converts_to_local_email_record_without_category():
    message = GmailMessage(
        sender="financeiro@empresa.com",
        subject="Relatorio mensal",
        body="O relatorio financeiro esta disponivel.",
        received_at="15 ago. 2026",
    )

    record = message.to_email_record()

    assert record.sender == "financeiro@empresa.com"
    assert record.subject == "Relatorio mensal"
    assert record.body == "O relatorio financeiro esta disponivel."
    assert record.received_at == "15 ago. 2026"
    assert record.category is None
