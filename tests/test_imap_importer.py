from email.message import EmailMessage
from threading import Event

import pytest

from email_classifier_app.imap_importer import ImapImportError, ImapImporter, ImapSettings


def make_message(body: str = "mensagem") -> bytes:
    message = EmailMessage()
    message["From"] = "Pessoa <pessoa@empresa.com>"
    message["To"] = "usuario@empresa.com"
    message["Subject"] = "Relatório de reunião"
    message["Date"] = "Wed, 28 Oct 2026 09:00:00 -0300"
    message.set_content(body)
    return message.as_bytes()


class FakeImap:
    def __init__(self, messages=None, fail_login=False, validity=b"777"):
        self.messages = messages or {b"5": make_message()}
        self.fail_login = fail_login
        self.validity = validity
        self.calls = []
        self.logged_out = False

    def login(self, user, password):
        self.calls.append(("login", user, password))
        if self.fail_login:
            raise RuntimeError("AUTHENTICATIONFAILED secret-password must not leak")
        return "OK", []

    def select(self, folder, readonly=False):
        self.calls.append(("select", folder, readonly))
        return "OK", [b"1"]

    def response(self, name):
        self.calls.append(("response", name))
        return name, [self.validity] if self.validity is not None else None

    def uid(self, command, uid, query):
        self.calls.append(("uid", command, uid, query))
        if command == "SEARCH":
            return "OK", [b"4 5"]
        raw = self.messages.get(uid)
        if raw is None:
            return "OK", []
        metadata = b"5 (UID 5 RFC822.SIZE " + str(len(raw)).encode() + b" BODY[] {" + str(len(raw)).encode() + b"}"
        return "OK", [(metadata, raw), b")"]

    def logout(self):
        self.logged_out = True
        return "BYE", []


def make_importer(fake, stop_event=None):
    return ImapImporter(
        ImapSettings("imap.kinghost.net", "usuario@empresa.com", "test-password", limit=2),
        stop_event=stop_event,
        client_factory=lambda *args, **kwargs: fake,
    )


def test_collects_parsed_message_in_readonly_mode_and_uses_peek_uid():
    fake = FakeImap(messages={b"4": make_message("antiga"), b"5": make_message("corpo com acentuação")})
    importer = make_importer(fake)
    records = []

    result = importer.collect(lambda record: records.append(record) or True)

    assert result.imported_count == 2
    assert [record.body.strip() for record in records] == ["corpo com acentuação", "antiga"]
    assert records[0].subject == "Relatório de reunião"
    assert records[0].sender == "Pessoa <pessoa@empresa.com>"
    assert records[0].received_at == "2026-10-28T09:00:00-03:00"
    assert records[0].source_key.startswith("imap:")
    assert records[0].source_key != records[1].source_key
    assert ("select", "INBOX", True) in fake.calls
    assert any(call[0:3] == ("uid", "FETCH", b"5") and call[3] == "(UID RFC822.SIZE)" for call in fake.calls)
    assert any(call[0:3] == ("uid", "FETCH", b"5") and "BODY.PEEK[]" in call[3] for call in fake.calls)
    assert fake.logged_out


def test_test_connection_never_searches_or_fetches():
    fake = FakeImap()

    make_importer(fake).test_connection()

    assert ("select", "INBOX", True) in fake.calls
    assert not [call for call in fake.calls if call[0] == "uid"]
    assert fake.logged_out


def test_authentication_error_does_not_expose_password():
    fake = FakeImap(fail_login=True)

    with pytest.raises(ImapImportError) as raised:
        make_importer(fake).test_connection()

    assert "test-password" not in str(raised.value)
    assert fake.logged_out


def test_cancel_before_fetch_closes_connection_without_fetch():
    stop = Event()
    stop.set()
    fake = FakeImap()

    result = make_importer(fake, stop).collect(lambda _record: True)

    assert result.cancelled
    assert result.imported_count == 0
    assert not [call for call in fake.calls if call[0:2] == ("uid", "FETCH")]
    assert fake.logged_out


def test_skips_message_with_only_html_when_stripping_leaves_no_text():
    message = EmailMessage()
    message["From"] = "a@example.com"
    message["Subject"] = "Promo"
    message.set_content("<html><head><style>.x { color:red }</style></head><body><script>alert(1)</script><p>Oferta</p></body></html>", subtype="html")
    fake = FakeImap(messages={b"4": message.as_bytes(), b"5": message.as_bytes()})
    records = []

    result = make_importer(fake).collect(lambda record: records.append(record) or True)

    assert result.imported_count == 2
    assert all(record.body == "Oferta" for record in records)


def test_skips_messages_larger_than_configured_limit():
    fake = FakeImap()
    importer = ImapImporter(
        ImapSettings("imap.kinghost.net", "usuario@empresa.com", "pw", limit=1, max_message_bytes=10),
        client_factory=lambda *args, **kwargs: fake,
    )

    result = importer.collect(lambda _record: True)

    assert result.imported_count == 0
    assert result.skipped_count == 1
    assert not any(call[0:2] == ("uid", "FETCH") and "BODY.PEEK[]" in call[3] for call in fake.calls)


def test_missing_uidvalidity_fails_safely_instead_of_creating_collision_prone_keys():
    fake = FakeImap(validity=None)

    with pytest.raises(ImapImportError, match="UIDVALIDITY"):
        make_importer(fake).collect(lambda _record: True)

    assert not [call for call in fake.calls if call[0:2] == ("uid", "SEARCH")]
    assert fake.logged_out


def test_unknown_mime_charset_falls_back_to_utf8():
    message = EmailMessage()
    message["From"] = "a@example.com"
    message["Subject"] = "Texto"
    message.set_content("café", cte="base64")
    message.replace_header("Content-Type", "text/plain; charset=x-unknown-charset")
    fake = FakeImap(messages={b"5": message.as_bytes()})
    records = []

    result = make_importer(fake).collect(lambda record: records.append(record) or True)

    assert result.imported_count == 1
    assert records[0].body.strip() == "café"
