from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
import re
from typing import Protocol
from uuid import uuid4

from .config import EMAIL_IMAGE_DIR
from .gmail_rpa import GmailMessage
from .ocr import LocalOcr
from .visual_capture import ScrollableCapture


GMAIL_INBOX_URL = "https://mail.google.com/mail/u/0/#inbox"
ProgressCallback = Callable[[str], None]


class DesktopGmailError(RuntimeError):
    """Erro de automacao da janela do Gmail aberta pelo usuario."""


class DesktopGmailReader(Protocol):
    def prepare_inbox(self) -> None: ...

    def read_message(self, index: int) -> GmailMessage: ...

    def finish(self) -> None: ...

    def recover(self) -> None: ...


class DesktopGmailImporter:
    """Coordena a leitura de mensagens no Chrome ja autenticado pelo usuario."""

    def __init__(
        self,
        max_messages: int = 10,
        reader: DesktopGmailReader | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        if max_messages < 1:
            raise ValueError("O limite de mensagens deve ser maior que zero.")
        self.max_messages = max_messages
        self.reader = reader or PyAutoGuiGmailReader()
        self.progress_callback = progress_callback or (lambda _message: None)
        self.failure_count = 0
        self.failure_messages: list[str] = []

    def import_inbox(self) -> list[GmailMessage]:
        self.progress_callback("Localizando a janela do Gmail aberta...")
        self.reader.prepare_inbox()
        self.failure_count = 0
        self.failure_messages = []
        messages: list[GmailMessage] = []
        try:
            for index in range(self.max_messages):
                self.progress_callback(f"Lendo mensagem {index + 1} de {self.max_messages}...")
                try:
                    messages.append(self.reader.read_message(index))
                except Exception as exc:
                    self.failure_count += 1
                    self.failure_messages.append(str(exc))
                    self.progress_callback(
                        f"Mensagem {index + 1} ignorada por seguranca: {str(exc)[:100]}"
                    )
                    recovery = getattr(self.reader, "recover", None)
                    if callable(recovery):
                        recovery()
        finally:
            self.reader.finish()
        if not messages:
            raise DesktopGmailError(
                "Nenhuma mensagem pode ser lida. Confirme que o Gmail esta na Caixa de entrada e tente novamente."
            )
        return messages


class PyAutoGuiGmailReader:
    """Leitor de tela para o Gmail em portugues, maximizado e com zoom de 100%."""

    def __init__(self, gui=None, clipboard=None, window_manager=None, capture=None, ocr=None) -> None:
        if gui is None or clipboard is None or window_manager is None:
            try:
                import pyautogui
                import pygetwindow
                import pyperclip
            except ImportError as exc:
                raise DesktopGmailError(
                    "As bibliotecas do RPA nao estao instaladas. Execute: python -m pip install -r requirements.txt"
                ) from exc
            gui = gui or pyautogui
            clipboard = clipboard or pyperclip
            window_manager = window_manager or pygetwindow
        self.gui = gui
        self.clipboard = clipboard
        self.window_manager = window_manager
        self.gui.PAUSE = 0.2
        self.width, self.height = self.gui.size()
        self.window = None
        self.capture = capture or ScrollableCapture(self.gui, EMAIL_IMAGE_DIR)
        self.ocr = ocr or LocalOcr()

    def prepare_inbox(self) -> None:
        if self.width < 1280 or self.height < 720:
            raise DesktopGmailError("Use uma tela com pelo menos 1280x720 para executar a leitura do Gmail.")
        self._focus_chrome()
        self.gui.hotkey("ctrl", "0")
        self.gui.sleep(0.5)

    def read_message(self, index: int) -> GmailMessage:
        row_x = int(self.width * 0.55)
        first_row_y = int(self.height * 0.273)
        row_height = max(25, int(self.height * 0.026))
        row_y = first_row_y + (index * row_height)

        self.gui.click(row_x, row_y)
        self.gui.sleep(1.4)
        opened_message = False
        capture_result = None
        try:
            capture_result = self.capture.capture(
                self._capture_name(index),
                region=self._message_region(),
                scroll_point=self._scroll_point(),
            )
            copied_text = self._copy_open_message()
            opened_message = self._looks_like_open_message(copied_text)
            if not opened_message:
                raise DesktopGmailError("A linha selecionada nao abriu uma mensagem valida do Gmail.")
            message = self._message_from_clipboard(copied_text, index + 1)
            ocr_text = ""
            ocr_status = "Sem texto detectado"
            if capture_result.image_path:
                try:
                    ocr_text = self.ocr.extract(capture_result.image_path)
                    ocr_status = "Concluido" if ocr_text else "Sem texto detectado"
                except Exception:
                    ocr_status = "Indisponivel"
            return GmailMessage(
                sender=message.sender,
                subject=message.subject,
                body=message.body,
                received_at=message.received_at,
                image_path=capture_result.image_path,
                ocr_text=ocr_text,
                capture_status=capture_result.status,
                ocr_status=ocr_status,
            )
        except Exception:
            if capture_result and capture_result.image_path:
                try:
                    Path(capture_result.image_path).unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        finally:
            if opened_message:
                self._return_to_inbox()
            else:
                self.recover()

    def finish(self) -> None:
        return None

    def recover(self) -> None:
        self._focus_chrome()
        title = str(getattr(self.window, "title", "")).lower()
        if "caixa de entrada" not in title and "inbox" not in title:
            self.gui.hotkey("alt", "left")
            self.gui.sleep(0.9)

    def _focus_chrome(self) -> None:
        if self.window is not None and getattr(self.window, "width", 0) > 0:
            window = self.window
        else:
            windows = [window for window in self.window_manager.getWindowsWithTitle("Google Chrome") if window.width > 0]
            preferred = [
                window for window in windows
                if any(term in str(getattr(window, "title", "")).lower() for term in ("gmail", "caixa de entrada", "inbox"))
            ]
            if not preferred:
                raise DesktopGmailError("Abra o Google Chrome na Caixa de entrada do Gmail e tente novamente.")
            window = preferred[0]
            self.window = window
        if window is None:
            raise DesktopGmailError("Abra o Google Chrome, entre no Gmail e tente novamente.")
        window.activate()
        if not window.isMaximized:
            window.maximize()
        self.gui.sleep(0.8)

    def _copy_open_message(self) -> str:
        self.clipboard.copy("")
        self.gui.hotkey("ctrl", "a")
        self.gui.hotkey("ctrl", "c")
        self.gui.sleep(0.5)
        copied_text = str(self.clipboard.paste() or "").strip()
        if not copied_text:
            raise DesktopGmailError("Nao foi possivel copiar o conteudo do e-mail aberto.")
        return copied_text

    def _return_to_inbox(self) -> None:
        self.gui.hotkey("alt", "left")
        self.gui.sleep(0.9)

    def _message_region(self) -> tuple[int, int, int, int]:
        left = int(self.width * 0.14)
        top = int(self.height * 0.215)
        right = int(self.width * 0.975)
        bottom = int(self.height * 0.94)
        return left, top, right - left, bottom - top

    def _scroll_point(self) -> tuple[int, int]:
        return int(self.width * 0.72), int(self.height * 0.68)

    @staticmethod
    def _looks_like_open_message(copied_text: str) -> bool:
        normalized = "\n".join(line.strip().lower() for line in copied_text.splitlines() if line.strip())
        has_counter = re.search(r"(?m)^\d+ de [\d.]+$", normalized) is not None
        has_recipient = re.search(r"(?m)^para (mim|\S+)", normalized) is not None
        has_sender = re.search(r"\b[^\s<>]+@[^\s<>]+\b", normalized) is not None
        return has_counter and has_recipient and has_sender

    @staticmethod
    def _capture_name(index: int) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"gmail_{stamp}_{index + 1}_{uuid4().hex[:8]}"

    @staticmethod
    def _message_from_clipboard(copied_text: str, position: int) -> GmailMessage:
        lines = [" ".join(line.split()) for line in copied_text.splitlines()]
        lines = [line for line in lines if line]
        inbox_counter = next((index for index, line in enumerate(lines) if re.fullmatch(r"\d+ de [\d.]+", line)), None)
        subject_index = inbox_counter + 1 if inbox_counter is not None and inbox_counter + 1 < len(lines) else None
        recipient_index = next((index for index, line in enumerate(lines) if line.lower() == "para mim"), None)

        subject = lines[subject_index] if subject_index is not None else f"Mensagem importada {position}"
        body_start = recipient_index + 1 if recipient_index is not None else (subject_index or 0) + 1
        body = "\n".join(lines[body_start:])
        sender = "Remetente nao informado"
        header_end = recipient_index if recipient_index is not None else len(lines)
        for line in lines[:header_end]:
            email_match = re.search(r"<([^<>\s]+@[^<>\s]+)>", line) or re.search(r"\b[^\s<>]+@[^\s<>]+\b", line)
            if email_match:
                sender = email_match.group(1) if "<" in line else email_match.group(0)
                break
        return GmailMessage(sender=sender, subject=subject[:220], body=body)
