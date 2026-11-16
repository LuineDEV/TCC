from __future__ import annotations

import hashlib
import imaplib
import re
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timezone
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from threading import Event
from typing import Any

from .importer import EmailRecord


class ImapImportError(RuntimeError):
    """Erro de conexão/coleta IMAP sem informação de autenticação."""


@dataclass(frozen=True)
class ImapSettings:
    host: str
    username: str
    password: str = field(repr=False)
    port: int = 993
    folder: str = "INBOX"
    limit: int = 20
    timeout: int = 15
    max_message_bytes: int = 10 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.host.strip() or not self.username.strip() or not self.password:
            raise ValueError("Informe servidor, e-mail e senha do IMAP.")
        if not 1 <= self.port <= 65535:
            raise ValueError("A porta do IMAP é inválida.")
        if self.limit < 1 or self.limit > 500:
            raise ValueError("O limite deve estar entre 1 e 500 e-mails.")
        if self.timeout < 1 or self.max_message_bytes < 1:
            raise ValueError("O timeout e o tamanho máximo precisam ser positivos.")
        if not self.folder.strip():
            raise ValueError("Informe a pasta da caixa de e-mail.")


@dataclass(frozen=True)
class ImapImportResult:
    imported_count: int
    skipped_count: int
    cancelled: bool


class _PlainTextFromHtml(HTMLParser):
    _ignored_tags = {"script", "style", "head", "title", "noscript"}
    _block_tags = {
        "address", "article", "blockquote", "br", "div", "footer", "h1", "h2", "h3",
        "h4", "header", "hr", "li", "ol", "p", "section", "table", "td", "th", "tr", "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._ignored_tags:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag in self._block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and tag in self._block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def _plain_body(message: Any) -> str:
    part = message.get_body(preferencelist=("plain",))
    if part is not None:
        try:
            return str(part.get_content()).strip()
        except (LookupError, UnicodeError, TypeError):
            payload = part.get_payload(decode=True)
            if payload:
                return _decode_payload(payload, part.get_content_charset()).strip()

    part = message.get_body(preferencelist=("html",))
    if part is None:
        return ""
    try:
        html = str(part.get_content())
    except (LookupError, UnicodeError, TypeError):
        payload = part.get_payload(decode=True) or b""
        html = _decode_payload(payload, part.get_content_charset())
    parser = _PlainTextFromHtml()
    parser.feed(html)
    parser.close()
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


def _decode_payload(payload: bytes, charset: str | None) -> str:
    try:
        return payload.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _parse_record(raw_message: bytes, source_key: str) -> EmailRecord:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    sender = str(message["From"] or "").strip()
    subject = str(message["Subject"] or "").strip()
    body = _plain_body(message)
    date_header = message["Date"]
    received_at = None
    if date_header:
        try:
            timestamp = parsedate_to_datetime(str(date_header))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            received_at = timestamp.isoformat(timespec="seconds")
        except (TypeError, ValueError, OverflowError):
            received_at = None
    return EmailRecord(sender=sender, subject=subject, body=body, received_at=received_at,
                       source_key=source_key)


class ImapImporter:
    """Leitura IMAP TLS, em modo somente leitura e com identificação UID estável."""

    def __init__(
        self,
        settings: ImapSettings,
        stop_event: Event | None = None,
        progress_callback: Callable[[str], None] | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.stop_event = stop_event or Event()
        self.progress_callback = progress_callback or (lambda _message: None)
        self.client_factory = client_factory or imaplib.IMAP4_SSL

    def _connect(self):
        client = self.client_factory(
            self.settings.host,
            self.settings.port,
            ssl_context=ssl.create_default_context(),
            timeout=self.settings.timeout,
        )
        try:
            client.login(self.settings.username, self.settings.password)
            status, _ = client.select(self.settings.folder, readonly=True)
            if status != "OK":
                raise ImapImportError("Não foi possível abrir a pasta IMAP em modo somente leitura.")
            return client
        except Exception:
            try:
                client.logout()
            except Exception:
                pass
            raise

    def test_connection(self) -> None:
        """Confirma autenticação e acesso somente leitura à pasta, sem baixar mensagens."""
        client = None
        try:
            client = self._connect()
        except ImapImportError:
            raise
        except Exception as exc:
            raise self._friendly_error(exc) from None
        finally:
            self._logout(client)

    def collect(self, on_record: Callable[[EmailRecord], bool | None]) -> ImapImportResult:
        """Emite os registros um por vez; callback True conta como salvo."""
        client = None
        imported = 0
        skipped = 0
        cancelled = False
        try:
            client = self._connect()
            if self.stop_event.is_set():
                return ImapImportResult(0, 0, True)
            validity = self._uid_validity(client)
            status, data = client.uid("SEARCH", None, "ALL")
            if status != "OK":
                raise ImapImportError("O servidor não conseguiu listar as mensagens dessa pasta.")
            uids = (data[0] if data else b"").split()[-self.settings.limit :]
            uids.reverse()
            total = len(uids)

            for index, uid in enumerate(uids, start=1):
                if self.stop_event.is_set():
                    cancelled = True
                    break
                self.progress_callback(f"Lendo e-mail {index} de {total}...")
                status, data = client.uid("FETCH", uid, "(UID RFC822.SIZE)")
                if status != "OK":
                    skipped += 1
                    continue
                reported_size = self._reported_size(data)
                if reported_size is None or reported_size > self.settings.max_message_bytes:
                    skipped += 1
                    continue
                if self.stop_event.is_set():
                    cancelled = True
                    break
                status, data = client.uid("FETCH", uid, "(UID BODY.PEEK[])")
                if status != "OK":
                    skipped += 1
                    continue
                raw_message = self._fetch_body(data)
                if not raw_message:
                    skipped += 1
                    continue
                key_material = "\0".join((self.settings.host.lower(), self.settings.username.lower(),
                                              self.settings.folder, validity, uid.decode("ascii", "replace")))
                source_key = "imap:" + hashlib.sha256(key_material.encode("utf-8")).hexdigest()
                record = _parse_record(raw_message, source_key)
                if not record.subject and not record.body:
                    skipped += 1
                    continue
                if on_record(record):
                    imported += 1
                else:
                    skipped += 1
            cancelled = cancelled or self.stop_event.is_set()
            return ImapImportResult(imported, skipped, cancelled)
        except ImapImportError:
            raise
        except Exception as exc:
            raise self._friendly_error(exc) from None
        finally:
            self._logout(client)

    def _uid_validity(self, client: Any) -> str:
        try:
            response = client.response("UIDVALIDITY")
        except Exception:
            response = None
        if response and response[1]:
            value = response[1][0]
            if isinstance(value, bytes):
                return value.decode("ascii", "replace")
            return str(value)
        raise ImapImportError(
            "O servidor IMAP não informou UIDVALIDITY; a importação foi cancelada para evitar duplicidades."
        )

    @staticmethod
    def _reported_size(data: list[Any]) -> int | None:
        for item in data or []:
            metadata = item[0] if isinstance(item, tuple) and item else item
            if isinstance(metadata, bytes):
                match = re.search(rb"RFC822\.SIZE\s+(\d+)", metadata, re.IGNORECASE)
                if match:
                    return int(match.group(1))
        return None

    @staticmethod
    def _fetch_body(data: list[Any]) -> bytes:
        raw_message = b""
        for item in data or []:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            metadata, payload = item[0], item[1]
            if not isinstance(metadata, bytes) or not isinstance(payload, bytes):
                continue
            if b"BODY[" in metadata.upper() or b"BODY.PEEK[" in metadata.upper():
                raw_message = payload
        return raw_message

    @staticmethod
    def _friendly_error(exc: BaseException) -> ImapImportError:
        text = str(exc).lower()
        if "auth" in text or "login" in text or "credential" in text or "password" in text:
            return ImapImportError("Falha de autenticação IMAP. Confira o e-mail e a senha informados.")
        if isinstance(exc, (TimeoutError,)) or "timed out" in text or "timeout" in text:
            return ImapImportError("O servidor IMAP demorou para responder. Confira a conexão e tente novamente.")
        if isinstance(exc, ssl.SSLError):
            return ImapImportError("Não foi possível validar a conexão segura com o servidor IMAP.")
        return ImapImportError("Não foi possível acessar o servidor IMAP. Confira servidor, porta e pasta.")

    @staticmethod
    def _logout(client: Any | None) -> None:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
