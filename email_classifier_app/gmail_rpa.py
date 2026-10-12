from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import sleep

from .config import GMAIL_PROFILE_DIR, ensure_directories
from .importer import EmailRecord


GMAIL_INBOX_URL = "https://mail.google.com/mail/u/0/#inbox"
ProgressCallback = Callable[[str], None]
MessageCollector = Callable[[int], list["GmailMessage"]]


class GmailImportError(RuntimeError):
    """Erro apresentado ao usuario quando a coleta no Gmail nao pode continuar."""


@dataclass(frozen=True)
class GmailMessage:
    sender: str
    subject: str
    body: str
    received_at: str | None = None
    image_path: str | None = None
    ocr_text: str = ""
    capture_status: str = "Somente texto"
    ocr_status: str = "Nao executado"

    def to_email_record(self) -> EmailRecord:
        return EmailRecord(
            sender=self.sender,
            subject=self.subject,
            body=self.body,
            received_at=self.received_at,
            image_path=self.image_path,
            ocr_text=self.ocr_text,
            capture_status=self.capture_status,
            ocr_status=self.ocr_status,
        )


class GmailInboxImporter:
    """Coleta mensagens da primeira pagina da Caixa de Entrada do Gmail."""

    def __init__(
        self,
        max_messages: int = 10,
        profile_dir: Path = GMAIL_PROFILE_DIR,
        progress_callback: ProgressCallback | None = None,
        collector: MessageCollector | None = None,
    ) -> None:
        if max_messages < 1:
            raise ValueError("O limite de mensagens deve ser maior que zero.")
        self.max_messages = max_messages
        self.profile_dir = profile_dir
        self.progress_callback = progress_callback or (lambda _message: None)
        self.collector = collector

    def import_inbox(self) -> list[GmailMessage]:
        if self.collector:
            return self.collector(self.max_messages)[: self.max_messages]
        return self._collect_with_playwright()

    def _collect_with_playwright(self) -> list[GmailMessage]:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise GmailImportError(
                "A biblioteca Playwright nao esta instalada. Execute: python -m pip install -r requirements.txt"
            ) from exc

        ensure_directories()
        self.progress_callback("Abrindo o Gmail no navegador...")
        try:
            with sync_playwright() as playwright:
                context = self._launch_browser(playwright)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(GMAIL_INBOX_URL, wait_until="domcontentloaded", timeout=60_000)
                    self.progress_callback("Faca login no Gmail na janela aberta, se for necessario.")
                    page.locator("tr.zA").first.wait_for(state="visible", timeout=300_000)
                    self.progress_callback("Lendo as mensagens da primeira pagina...")
                    return self._collect_messages(page)
                finally:
                    context.close()
        except GmailImportError:
            raise
        except PlaywrightError as exc:
            raise GmailImportError(
                "Nao foi possivel acessar a Caixa de Entrada do Gmail. "
                "Verifique o login e tente novamente."
            ) from exc

    def _launch_browser(self, playwright):
        errors: list[str] = []
        for channel in ("chrome", "msedge"):
            try:
                return playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    channel=channel,
                    headless=False,
                    viewport={"width": 1360, "height": 860},
                )
            except Exception as exc:
                errors.append(f"{channel}: {exc}")
        raise GmailImportError(
            "Nao foi encontrado Google Chrome ou Microsoft Edge para abrir o Gmail. "
            "Instale um desses navegadores e tente novamente."
        )

    def _collect_messages(self, page) -> list[GmailMessage]:
        messages: list[GmailMessage] = []
        row_count = page.locator("tr.zA").count()
        if row_count == 0:
            raise GmailImportError("Nenhuma mensagem foi encontrada na primeira pagina da Caixa de Entrada.")

        for index in range(min(row_count, self.max_messages)):
            rows = page.locator("tr.zA")
            row = rows.nth(index)
            was_unread = "zE" in (row.get_attribute("class") or "").split()
            received_at = self._text_from(row, ".xW.xY") or self._text_from(row, ".xW")

            self.progress_callback(f"Coletando mensagem {index + 1} de {min(row_count, self.max_messages)}...")
            row.click()
            page.locator("h2.hP, [role='main'] h2").first.wait_for(state="visible", timeout=30_000)
            page.wait_for_timeout(400)

            message = GmailMessage(
                sender=self._text_from(page, ".gD[email]") or self._text_from(page, ".gD") or "Remetente nao informado",
                subject=self._text_from(page, "h2.hP") or self._text_from(page, "[role='main'] h2") or "Sem assunto",
                body=self._text_from(page, ".a3s.aiL") or self._text_from(page, ".a3s") or "",
                received_at=received_at or None,
            )
            messages.append(message)

            if was_unread:
                self._mark_current_message_as_unread(page)
            page.go_back(wait_until="domcontentloaded")
            page.locator("tr.zA").first.wait_for(state="visible", timeout=30_000)
            sleep(0.25)

        return messages

    @staticmethod
    def _text_from(scope, selector: str) -> str:
        locator = scope.locator(selector).first
        if locator.count() == 0:
            return ""
        try:
            return " ".join(locator.inner_text(timeout=5_000).split())
        except Exception:
            return ""

    @staticmethod
    def _mark_current_message_as_unread(page) -> None:
        page.keyboard.press("Shift+u")
        page.wait_for_timeout(250)
