import pytest
from threading import Event

from email_classifier_app.desktop_rpa import DesktopGmailError, DesktopGmailImporter, PyAutoGuiGmailReader
from email_classifier_app.gmail_rpa import GmailMessage
from email_classifier_app.visual_capture import CaptureResult


class FakeDesktopReader:
    def __init__(self) -> None:
        self.prepared = False
        self.finished = False
        self.requested_indexes: list[int] = []

    def prepare_inbox(self) -> None:
        self.prepared = True

    def read_message(self, index: int) -> GmailMessage:
        self.requested_indexes.append(index)
        return GmailMessage(
            sender=f"remetente{index}@email.com",
            subject=f"Assunto {index}",
            body=f"Corpo {index}",
        )

    def finish(self) -> None:
        self.finished = True

    def recover(self) -> None:
        return None


def test_desktop_importer_reads_only_the_configured_number_of_messages():
    reader = FakeDesktopReader()

    messages = DesktopGmailImporter(max_messages=3, reader=reader).import_inbox()

    assert reader.prepared is True
    assert reader.requested_indexes == [0, 1, 2]
    assert reader.finished is True
    assert [message.subject for message in messages] == ["Assunto 0", "Assunto 1", "Assunto 2"]


class ReaderWithOneBrokenMessage(FakeDesktopReader):
    def __init__(self) -> None:
        super().__init__()
        self.recoveries = 0

    def read_message(self, index: int) -> GmailMessage:
        self.requested_indexes.append(index)
        if index == 1:
            raise RuntimeError("layout inesperado")
        return GmailMessage(sender="a@email.com", subject=f"Assunto {index}", body="Corpo")

    def recover(self) -> None:
        self.recoveries += 1


def test_desktop_importer_skips_broken_message_and_continues():
    reader = ReaderWithOneBrokenMessage()
    progress: list[str] = []
    importer = DesktopGmailImporter(max_messages=3, reader=reader, progress_callback=progress.append)

    messages = importer.import_inbox()

    assert [message.subject for message in messages] == ["Assunto 0", "Assunto 2"]
    assert reader.recoveries == 1
    assert importer.failure_count == 1
    assert any("ignorada" in message.lower() for message in progress)


def test_desktop_importer_stops_after_current_message_and_keeps_completed_messages():
    stop_event = Event()

    class StopsAfterFirstMessage(FakeDesktopReader):
        def read_message(self, index: int) -> GmailMessage:
            message = super().read_message(index)
            stop_event.set()
            return message

    reader = StopsAfterFirstMessage()
    importer = DesktopGmailImporter(max_messages=10, reader=reader, stop_event=stop_event)
    messages = importer.import_inbox()

    assert len(messages) == 1
    assert importer.cancelled is True
    assert reader.finished is True


class AlwaysBrokenReader(FakeDesktopReader):
    def read_message(self, index: int) -> GmailMessage:
        raise RuntimeError("nao abriu")


def test_desktop_importer_reports_error_when_every_message_fails():
    with pytest.raises(DesktopGmailError, match="Nenhuma mensagem"):
        DesktopGmailImporter(max_messages=2, reader=AlwaysBrokenReader()).import_inbox()


class FakeGui:
    PAUSE = 0

    def __init__(self) -> None:
        self.hotkeys: list[tuple[str, ...]] = []

    def size(self):
        return (1920, 1080)

    def sleep(self, _seconds: float) -> None:
        return None

    def hotkey(self, *keys: str) -> None:
        self.hotkeys.append(keys)


class FakeWindow:
    width = 1920
    isMaximized = True
    title = "Caixa de entrada (10) - Gmail - Google Chrome"

    def activate(self) -> None:
        return None

    def maximize(self) -> None:
        return None


class FakeWindowManager:
    @staticmethod
    def getWindowsWithTitle(_title: str):
        return [FakeWindow()]


def test_prepare_inbox_only_focuses_existing_chrome_window():
    gui = FakeGui()
    reader = PyAutoGuiGmailReader(
        gui=gui,
        clipboard=object(),
        window_manager=FakeWindowManager(),
    )

    reader.prepare_inbox()

    assert gui.hotkeys == [("ctrl", "0")]


def test_clipboard_parser_extracts_subject_sender_and_body_from_gmail_screen_text():
    copied_text = """
    Nenhum selecionado
    Pular para o conteúdo
    10 de 8.559
    Estagiário (TI) - Suporte a Sistemas - N1 | Brasil na empresa Voke
    Alertas de vaga do LinkedIn <jobalerts-noreply@linkedin.com>
    sex., 14 de ago., 08:11 (há 1 dia)
    para mim
    LinkedIn
    Novas vagas correspondem às suas preferências de localidade.
    Voke
    Estagiário (TI) - Suporte a Sistemas - N1 | Brasil
    """

    message = PyAutoGuiGmailReader._message_from_clipboard(copied_text, position=1)

    assert message.subject == "Estagiário (TI) - Suporte a Sistemas - N1 | Brasil na empresa Voke"
    assert message.sender == "jobalerts-noreply@linkedin.com"
    assert "Novas vagas correspondem" in message.body
    assert "Nenhum selecionado" not in message.body


def test_open_message_validation_rejects_inbox_or_external_page_text():
    assert PyAutoGuiGmailReader._looks_like_open_message("Caixa de entrada\n1-50 de 500") is False
    assert PyAutoGuiGmailReader._looks_like_open_message("Oferta imperdivel\nComprar agora") is False
    assert PyAutoGuiGmailReader._looks_like_open_message("10 de 500\nAssunto\nPessoa <a@b.com>\npara mim\nCorpo") is True


class CopyGui:
    PAUSE = 0

    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []
        self.hotkeys: list[tuple[str, ...]] = []

    def size(self):
        return (1920, 1080)

    def sleep(self, _seconds: float) -> None:
        return None

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    def hotkey(self, *keys: str) -> None:
        self.hotkeys.append(keys)


class CopyClipboard:
    def copy(self, _text: str) -> None:
        return None

    @staticmethod
    def paste() -> str:
        return "Assunto do e-mail\nCorpo do e-mail"


def test_copy_and_return_do_not_click_inside_email_content():
    gui = CopyGui()
    reader = PyAutoGuiGmailReader(gui=gui, clipboard=CopyClipboard(), window_manager=FakeWindowManager())

    copied = reader._copy_open_message()
    reader._return_to_inbox()

    assert copied == "Assunto do e-mail\nCorpo do e-mail"
    assert gui.clicks == []
    assert gui.hotkeys == [("ctrl", "a"), ("ctrl", "c"), ("alt", "left")]


class OrderedGui(CopyGui):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def click(self, x: int, y: int) -> None:
        self.events.append("open-message")

    def hotkey(self, *keys: str) -> None:
        self.events.append("hotkey:" + "+".join(keys))


class OrderedClipboard:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def copy(self, _text: str) -> None:
        self.events.append("clipboard-clear")

    def paste(self) -> str:
        return "10 de 500\nAssunto\nPessoa <a@b.com>\npara mim\nCorpo"


class OrderedCapture:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def capture(self, name, region, scroll_point, stop_event=None):
        self.events.append("capture")
        return CaptureResult(None, "Somente texto", 1)


def test_visual_capture_happens_before_ctrl_a_selection():
    events: list[str] = []
    reader = PyAutoGuiGmailReader(
        gui=OrderedGui(events),
        clipboard=OrderedClipboard(events),
        window_manager=FakeWindowManager(),
        capture=OrderedCapture(events),
        ocr=object(),
    )

    reader.read_message(0)

    assert events.index("capture") < events.index("hotkey:ctrl+a")
