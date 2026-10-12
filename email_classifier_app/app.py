from __future__ import annotations

from queue import Empty, Queue
from pathlib import Path
from threading import Thread
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from .config import DATA_DIR
from .database import JsonCacheRepository, MySQLRepository, create_repository
from .desktop_rpa import DesktopGmailImporter, PyAutoGuiGmailReader
from .gmail_rpa import GmailMessage
from .importer import load_emails_from_csv
from .model import CATEGORIES, DEFAULT_TRAINING_CSV, EmailClassifier
from .reader_presenter import build_extracted_text, capture_summary, format_received_at


CATEGORY_STYLES = {
    "Urgente": {"bg": "#4c1d1d", "fg": "#ffb4ab", "border": "#7f1d1d"},
    "Trabalho": {"bg": "#172554", "fg": "#bfdbfe", "border": "#1d4ed8"},
    "Pessoal": {"bg": "#052e16", "fg": "#bbf7d0", "border": "#15803d"},
    "Sem categoria": {"bg": "#27272a", "fg": "#d4d4d8", "border": "#3f3f46"},
}

MAX_RENDERED_EMAILS = 80
APP_BG = "#101114"
TOPBAR_BG = "#181a1f"
SIDEBAR_BG = "#15171c"
PANEL_BG = "#1b1e24"
PANEL_HOVER = "#232730"
BORDER = "#30343c"
MUTED_TEXT = "#a7adb8"
PRIMARY_TEXT = "#f4f6fa"


class EmailClassifierApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Organizador de E-mails")
        self.geometry("1400x800")
        self.minsize(1180, 700)
        self.configure(fg_color=APP_BG)

        self.repository: MySQLRepository | JsonCacheRepository
        self.repository, self.storage_status = create_repository()
        self.classifier = EmailClassifier()
        self.current_filter = "Todas"
        self.selected_email: dict | None = None
        self.filter_var = ctk.StringVar(value="Todas")
        self.search_var = ctk.StringVar()
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.count_labels: dict[str, ctk.CTkLabel] = {}
        self.email_rows: dict[int, tuple[ctk.CTkFrame, ctk.CTkFrame]] = {}
        self.email_cache: list[dict] = []
        self.search_after_id: str | None = None
        self.gmail_import_running = False
        self.gmail_events: Queue[tuple[str, object]] = Queue()
        self.reader_image: ctk.CTkImage | None = None
        self.reader_view = "Mensagem"

        self._build_layout()
        self._set_status("Carregando dados...", success=True)
        self.reload_emails()
        self.after(80, self._bootstrap_model)
        self.after(150, self._process_gmail_events)
        self.after(250, self._repair_legacy_gmail_imports)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, minsize=220)
        self.grid_columnconfigure(1, minsize=500, weight=1)
        self.grid_columnconfigure(2, minsize=560, weight=2)
        self.grid_rowconfigure(0, minsize=64)
        self.grid_rowconfigure(1, weight=1)

        self._build_topbar()
        self._build_sidebar()
        self._build_message_list()
        self._build_reading_pane()

    def _build_topbar(self) -> None:
        self.topbar = ctk.CTkFrame(self, fg_color=TOPBAR_BG, corner_radius=0, height=64)
        self.topbar.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.topbar.grid_columnconfigure(1, weight=1)

        brand = ctk.CTkLabel(
            self.topbar,
            text="Mail Desk",
            text_color=PRIMARY_TEXT,
            font=ctk.CTkFont(size=19, weight="bold"),
            anchor="w",
        )
        brand.grid(row=0, column=0, sticky="w", padx=(20, 18), pady=12)

        self.search_entry = ctk.CTkEntry(
            self.topbar,
            textvariable=self.search_var,
            placeholder_text="Pesquisar e-mails",
            height=38,
            corner_radius=4,
            fg_color="#24272d",
            border_width=1,
            border_color=BORDER,
            text_color=PRIMARY_TEXT,
        )
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 18), pady=12)
        self.search_entry.bind("<KeyRelease>", lambda _event: self._schedule_search_refresh())

        actions = ctk.CTkFrame(self.topbar, fg_color="transparent")
        actions.grid(row=0, column=2, sticky="e", padx=(0, 18), pady=12)

        self.sample_button = self._topbar_button(actions, "Exemplos", self.import_sample_csv, column=0, tertiary=True)
        self.classify_button = self._topbar_button(actions, "Classificar", self.classify_all, column=1)
        self.train_button = self._topbar_button(actions, "Treinar", self.train_model, column=2, secondary=True)
        self.clear_button = self._topbar_button(actions, "Limpar e-mails", self.clear_emails, column=3, secondary=True, width=116)

    def _build_sidebar(self) -> None:
        self.sidebar = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(10, weight=1)

        self.gmail_button = ctk.CTkButton(
            self.sidebar,
            text="Importar do Gmail",
            command=self.import_gmail,
            height=42,
            corner_radius=4,
            fg_color="#292d35",
            hover_color="#363b45",
            text_color=PRIMARY_TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.gmail_button.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 8))

        self.import_button = ctk.CTkButton(
            self.sidebar,
            text="Importar CSV",
            command=self.import_csv,
            height=34,
            corner_radius=4,
            fg_color="#1e2127",
            hover_color="#292d35",
            border_width=1,
            border_color=BORDER,
            text_color=MUTED_TEXT,
        )
        self.import_button.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))

        mailbox_title = ctk.CTkLabel(
            self.sidebar,
            text="Caixas",
            text_color=MUTED_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        mailbox_title.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 8))

        for row, label in enumerate(["Todas", *CATEGORIES], start=3):
            self._add_nav_item(row, label)

        status_card = ctk.CTkFrame(
            self.sidebar,
            fg_color="#20232a",
            corner_radius=3,
            border_width=1,
            border_color=BORDER,
        )
        status_card.grid(row=11, column=0, sticky="ew", padx=16, pady=(12, 18))
        status_card.grid_columnconfigure(0, weight=1)

        self.storage_label = ctk.CTkLabel(
            status_card,
            text=self._friendly_storage_status(),
            text_color=PRIMARY_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.storage_label.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))

        self.status_label = ctk.CTkLabel(
            status_card,
            text="Preparando...",
            text_color=MUTED_TEXT,
            anchor="w",
            wraplength=178,
        )
        self.status_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 12))

    def _build_message_list(self) -> None:
        self.list_panel = ctk.CTkFrame(
            self,
            fg_color=PANEL_BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
        )
        self.list_panel.grid(row=1, column=1, sticky="nsew")
        self.list_panel.grid_columnconfigure(0, weight=1)
        self.list_panel.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self.list_panel, fg_color=PANEL_BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(0, weight=1)

        self.folder_title = ctk.CTkLabel(
            header,
            text="Caixa de entrada",
            text_color=PRIMARY_TEXT,
            font=ctk.CTkFont(size=21, weight="bold"),
            anchor="w",
        )
        self.folder_title.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 0))

        self.folder_meta = ctk.CTkLabel(
            header,
            text="0 mensagens",
            text_color=MUTED_TEXT,
            anchor="w",
        )
        self.folder_meta.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 14))

        divider = ctk.CTkFrame(self.list_panel, height=1, fg_color=BORDER, corner_radius=0)
        divider.grid(row=1, column=0, sticky="ew")

        self.email_list = ctk.CTkScrollableFrame(self.list_panel, fg_color=PANEL_BG, corner_radius=0)
        self.email_list.grid(row=2, column=0, sticky="nsew")
        self.email_list.grid_columnconfigure(0, weight=1)

    def _build_reading_pane(self) -> None:
        self.detail_panel = ctk.CTkFrame(self, fg_color="#171a20", corner_radius=0)
        self.detail_panel.grid(row=1, column=2, sticky="nsew")
        self.detail_panel.grid_columnconfigure(0, weight=1)
        self.detail_panel.grid_rowconfigure(5, weight=1)

        self.reader_toolbar = ctk.CTkFrame(self.detail_panel, fg_color="transparent", corner_radius=0)
        self.reader_toolbar.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 0))
        self.reader_toolbar.grid_columnconfigure(1, weight=1)
        self.detail_badge = ctk.CTkLabel(
            self.reader_toolbar, text="", width=96, height=24, corner_radius=3,
            fg_color="#262a31", text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.detail_badge.grid(row=0, column=0, sticky="w")
        self.capture_state = ctk.CTkLabel(
            self.reader_toolbar, text="Somente texto", text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=12), anchor="e",
        )
        self.capture_state.grid(row=0, column=1, sticky="e")

        self.detail_title = ctk.CTkLabel(
            self.detail_panel, text="Nenhuma mensagem selecionada",
            font=ctk.CTkFont(size=22, weight="bold"), text_color=PRIMARY_TEXT,
            wraplength=620, justify="left", anchor="w",
        )
        self.detail_title.grid(row=1, column=0, sticky="ew", padx=26, pady=(12, 6))
        self.detail_meta = ctk.CTkLabel(
            self.detail_panel, text="", text_color=MUTED_TEXT, justify="left", anchor="w",
        )
        self.detail_meta.grid(row=2, column=0, sticky="ew", padx=26, pady=(0, 16))

        correction_bar = ctk.CTkFrame(
            self.detail_panel, fg_color="#20242b", corner_radius=3,
            border_width=1, border_color=BORDER,
        )
        correction_bar.grid(row=3, column=0, sticky="ew", padx=26, pady=(0, 14))
        correction_bar.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(
            correction_bar, text="Categoria", text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, padx=(14, 10), pady=10)
        self.manual_category = ctk.CTkOptionMenu(
            correction_bar, values=list(CATEGORIES), width=156, height=34, corner_radius=3,
            fg_color="#2a2f38", button_color="#3a404a", button_hover_color="#464d58",
            dropdown_fg_color="#24272d", dropdown_hover_color="#30343c",
            dropdown_text_color=PRIMARY_TEXT, text_color=PRIMARY_TEXT,
            state="disabled",
        )
        self.manual_category.grid(row=0, column=1, sticky="w", pady=10)
        self.manual_button = ctk.CTkButton(
            correction_bar, text="Salvar categoria", command=self.save_manual_category,
            width=132, height=34, corner_radius=3, fg_color="#303641",
            hover_color="#3c4451", text_color=PRIMARY_TEXT,
            state="disabled",
        )
        self.manual_button.grid(row=0, column=3, sticky="e", padx=12, pady=10)

        tabs = ctk.CTkFrame(self.detail_panel, fg_color="transparent", corner_radius=0)
        tabs.grid(row=4, column=0, sticky="ew", padx=26)
        tabs.grid_columnconfigure(2, weight=1)
        self.message_tab = ctk.CTkButton(
            tabs, text="Mensagem", command=lambda: self._show_reader_view("Mensagem"),
            width=92, height=34, corner_radius=2, fg_color="#2b3038",
            hover_color="#343a44", text_color=PRIMARY_TEXT,
        )
        self.message_tab.grid(row=0, column=0, padx=(0, 6))
        self.text_tab = ctk.CTkButton(
            tabs, text="Texto extraido", command=lambda: self._show_reader_view("Texto extraido"),
            width=112, height=34, corner_radius=2, fg_color="transparent",
            hover_color="#252a31", text_color=MUTED_TEXT,
        )
        self.text_tab.grid(row=0, column=1)

        self.reader_content = ctk.CTkFrame(self.detail_panel, fg_color="#121418", corner_radius=0)
        self.reader_content.grid(row=5, column=0, sticky="nsew", padx=26, pady=(10, 22))
        self.reader_content.grid_columnconfigure(0, weight=1)
        self.reader_content.grid_rowconfigure(0, weight=1)
        self.image_view = ctk.CTkScrollableFrame(
            self.reader_content, fg_color="#121418", corner_radius=0,
            border_width=1, border_color=BORDER,
        )
        self.image_view.grid(row=0, column=0, sticky="nsew")
        self.image_view.grid_columnconfigure(0, weight=1)
        self.image_label = ctk.CTkLabel(
            self.image_view, text="Selecione uma mensagem para visualizar a captura.",
            text_color=MUTED_TEXT, justify="center",
        )
        self.image_label.grid(row=0, column=0, sticky="n", padx=16, pady=24)
        self.body_text = ctk.CTkTextbox(
            self.reader_content, wrap="word", fg_color="#121418", border_width=1,
            border_color=BORDER, text_color="#e8ebf0", font=ctk.CTkFont(size=14),
        )
        self.body_text.grid(row=0, column=0, sticky="nsew")
        self.body_text.grid_remove()
        self.body_text.insert("1.0", "O conteudo da mensagem aparecera aqui.")
        self.body_text.configure(state="disabled")

    def _build_reading_pane_legacy(self) -> None:
        self.detail_panel = ctk.CTkFrame(self, fg_color="#171a20", corner_radius=0)
        self.detail_panel.grid(row=1, column=2, sticky="nsew")
        self.detail_panel.grid_columnconfigure(0, weight=1)
        self.detail_panel.grid_rowconfigure(4, weight=1)

        self.reader_toolbar = ctk.CTkFrame(self.detail_panel, fg_color="#171a20", corner_radius=0)
        self.reader_toolbar.grid(row=0, column=0, sticky="ew")
        self.reader_toolbar.grid_columnconfigure(0, weight=1)

        self.detail_badge = ctk.CTkLabel(
            self.reader_toolbar,
            text="",
            width=112,
            height=28,
            corner_radius=3,
            fg_color="#262a31",
            text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.detail_badge.grid(row=0, column=0, sticky="w", padx=24, pady=(18, 10))

        self.detail_title = ctk.CTkLabel(
            self.detail_panel,
            text="Nenhuma mensagem selecionada",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=PRIMARY_TEXT,
            wraplength=560,
            justify="left",
            anchor="w",
        )
        self.detail_title.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 8))

        self.detail_meta = ctk.CTkLabel(
            self.detail_panel,
            text="",
            text_color=MUTED_TEXT,
            justify="left",
            anchor="w",
        )
        self.detail_meta.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 18))

        correction_bar = ctk.CTkFrame(
            self.detail_panel,
            fg_color="#20242b",
            corner_radius=3,
            border_width=1,
            border_color=BORDER,
        )
        correction_bar.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 18))
        correction_bar.grid_columnconfigure(0, weight=1)

        correction_label = ctk.CTkLabel(
            correction_bar,
            text="Categoria",
            text_color=MUTED_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        correction_label.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))

        self.manual_category = ctk.CTkOptionMenu(
            correction_bar,
            values=list(CATEGORIES),
            width=170,
            height=34,
            corner_radius=4,
            fg_color="#2a2f38",
            button_color="#3a404a",
            button_hover_color="#464d58",
            dropdown_fg_color="#24272d",
            dropdown_hover_color="#30343c",
            dropdown_text_color=PRIMARY_TEXT,
            text_color=PRIMARY_TEXT,
        )
        self.manual_category.grid(row=1, column=0, sticky="w", padx=14, pady=(4, 12))

        self.manual_button = ctk.CTkButton(
            correction_bar,
            text="Salvar alteração",
            command=self.save_manual_category,
            width=132,
            height=34,
            corner_radius=4,
            fg_color="#303641",
            hover_color="#3c4451",
            text_color=PRIMARY_TEXT,
        )
        self.manual_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=14, pady=12)

        self.body_text = ctk.CTkTextbox(
            self.detail_panel,
            wrap="word",
            fg_color="#171a20",
            border_width=0,
            text_color="#e8ebf0",
            font=ctk.CTkFont(size=14),
        )
        self.body_text.grid(row=4, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self.body_text.insert("1.0", "O conteúdo da mensagem aparecerá aqui.")
        self.body_text.configure(state="disabled")

    def _topbar_button(
        self,
        parent: ctk.CTkFrame,
        text: str,
        command,
        column: int,
        secondary: bool = False,
        tertiary: bool = False,
        width: int = 92,
    ) -> ctk.CTkButton:
        fg_color = "#292d35"
        hover_color = "#363b45"
        border_width = 1
        if secondary:
            fg_color = "#20232a"
            hover_color = "#292d35"
        if tertiary:
            fg_color = "transparent"
            hover_color = "#292d35"
            border_width = 0
        button = ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=34,
            corner_radius=4,
            fg_color=fg_color,
            hover_color=hover_color,
            text_color=MUTED_TEXT if secondary or tertiary else PRIMARY_TEXT,
            border_width=border_width,
            border_color=BORDER,
            font=ctk.CTkFont(size=13, weight="bold" if not secondary else "normal"),
        )
        button.grid(row=0, column=column, padx=(0, 8))
        return button

    def _add_nav_item(self, row: int, label: str) -> None:
        button = ctk.CTkButton(
            self.sidebar,
            text=label,
            command=lambda item=label: self.apply_filter(item),
            height=38,
            corner_radius=3,
            fg_color="transparent",
            hover_color=PANEL_HOVER,
            text_color=MUTED_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=14, weight="normal"),
        )
        button.grid(row=row, column=0, sticky="ew", padx=12, pady=1)
        self.nav_buttons[label] = button

        count = ctk.CTkLabel(button, text="0", text_color=MUTED_TEXT, width=34, fg_color="transparent")
        count.place(relx=0.94, rely=0.50, anchor="e")
        self.count_labels[label] = count

    def _bootstrap_model(self) -> None:
        try:
            self.classifier.ensure_model()
            self._set_status("Modelo pronto", success=True)
        except Exception:
            self._set_status("Treinamento pendente", success=False)

    def _friendly_storage_status(self) -> str:
        if isinstance(self.repository, MySQLRepository):
            return "Banco local conectado"
        return "Modo demonstração"

    def _set_status(self, text: str, success: bool = True) -> None:
        self.status_label.configure(text=text, text_color="#d4d4d8" if success else "#a3a3a3")

    def import_sample_csv(self) -> None:
        self._import_records(DEFAULT_TRAINING_CSV)

    def import_csv(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Selecione um CSV de e-mails",
            initialdir=str(DATA_DIR),
            filetypes=[("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")],
        )
        if file_path:
            self._import_records(Path(file_path))

    def import_gmail(self) -> None:
        if self.gmail_import_running:
            return
        messagebox.showinfo(
            "Leitura do Gmail",
            "Deixe o Google Chrome aberto no Gmail, com a Caixa de Entrada visivel, "
            "a janela maximizada e o zoom em 100%.\n\n"
            "Durante a leitura, nao use o mouse ou o teclado.",
        )
        self.gmail_import_running = True
        self.gmail_button.configure(state="disabled", text="Lendo Gmail...")
        self._set_status("Preparando leitura do Gmail aberto...", success=True)
        Thread(target=self._collect_gmail_in_background, daemon=True).start()

    def _collect_gmail_in_background(self) -> None:
        def report_progress(message: str) -> None:
            self.gmail_events.put(("progress", message))

        try:
            importer = DesktopGmailImporter(max_messages=10, progress_callback=report_progress)
            messages = importer.import_inbox()
            self.gmail_events.put(("success", (messages, importer.failure_count)))
        except Exception as exc:
            self.gmail_events.put(("error", str(exc)))

    def _process_gmail_events(self) -> None:
        try:
            while True:
                event, payload = self.gmail_events.get_nowait()
                if event == "progress":
                    self._set_status(str(payload), success=True)
                elif event == "success":
                    self._finish_gmail_import(payload)
                elif event == "error":
                    self._finish_gmail_import_error(str(payload))
        except Empty:
            pass
        self.after(150, self._process_gmail_events)

    def _finish_gmail_import(self, messages: object) -> None:
        failure_count = 0
        if isinstance(messages, tuple) and len(messages) == 2:
            messages, failure_count = messages
        records = [message.to_email_record() for message in messages if isinstance(message, GmailMessage)]
        try:
            imported, skipped = self._save_records(records)
            self.repository.log("INFO", f"{imported} e-mails importados do Gmail")
            self.reload_emails()
            self._set_status("Importacao do Gmail concluida", success=True)
            message = f"{imported} e-mails do Gmail foram importados e classificados."
            if skipped:
                message += f"\n{skipped} duplicados foram ignorados."
            if failure_count:
                message += f"\n{failure_count} mensagens foram ignoradas com seguranca."
            messagebox.showinfo("Importacao do Gmail concluida", message)
        except Exception as exc:
            messagebox.showerror("Erro ao salvar e-mails do Gmail", str(exc))
            self._set_status("Falha ao salvar importacao", success=False)
        finally:
            self.gmail_import_running = False
            self.gmail_button.configure(state="normal", text="Importar do Gmail")

    def _finish_gmail_import_error(self, error_message: str) -> None:
        self.gmail_import_running = False
        self.gmail_button.configure(state="normal", text="Importar do Gmail")
        self._set_status("Importacao do Gmail interrompida", success=False)
        messagebox.showerror("Erro ao importar do Gmail", error_message)

    def _import_records(self, path: Path) -> None:
        try:
            records = load_emails_from_csv(path)
            imported, skipped = self._save_records(records)
            self.repository.log("INFO", f"{imported} e-mails importados de {path.name}")
            self.reload_emails()
            message = f"{imported} e-mails foram importados."
            if skipped:
                message += f"\n{skipped} duplicados foram ignorados."
            messagebox.showinfo("Importação concluída", message)
        except Exception as exc:
            messagebox.showerror("Erro ao importar", str(exc))

    def _save_records(self, records) -> tuple[int, int]:
        existing_keys = {
            self._record_key(
                str(email.get("sender", "")),
                str(email.get("subject", "")),
                str(email.get("body", "")),
            )
            for email in self.email_cache
        }
        if any(not record.category for record in records):
            self.classifier.ensure_model()

        imported = 0
        skipped = 0
        for record in records:
            key = self._record_key(record.sender, record.subject, record.body)
            if key in existing_keys:
                skipped += 1
                continue
            if not record.category:
                prediction = self.classifier.predict(
                    record.subject, record.body, record.ocr_text, sender=record.sender
                )
                record.category = prediction.category
                record.confidence = prediction.confidence
            self.repository.save_email(record)
            existing_keys.add(key)
            imported += 1
        return imported, skipped

    def clear_emails(self) -> None:
        count = len(self.email_cache)
        if count == 0:
            messagebox.showinfo("Nenhum e-mail", "Nao ha e-mails salvos para remover.")
            return
        confirmed = messagebox.askyesno(
            "Limpar e-mails",
            f"Remover os {count} e-mails salvos localmente?\n\n"
            "O modelo treinado sera mantido e continuara aprendendo nas proximas importacoes.",
            icon="warning",
        )
        if not confirmed:
            return

        removed = self.repository.clear_emails()
        self.repository.log("INFO", f"{removed} e-mails removidos da base local; modelo mantido")
        self.selected_email = None
        self._reset_detail_pane()
        self.reload_emails()
        self._set_status("E-mails removidos; modelo mantido", success=True)
        messagebox.showinfo("E-mails removidos", f"{removed} e-mails foram removidos. O modelo foi mantido.")

    def _reset_detail_pane(self) -> None:
        self.detail_badge.configure(text="", fg_color="#262a31", text_color=MUTED_TEXT)
        self.detail_title.configure(text="Nenhuma mensagem selecionada")
        self.detail_meta.configure(text="")
        self.capture_state.configure(text="Somente texto")
        self.manual_category.configure(state="disabled")
        self.manual_button.configure(state="disabled")
        self.reader_image = None
        self.image_label.configure(image=None, text="Selecione uma mensagem para visualizar a captura.")
        self.body_text.configure(state="normal")
        self.body_text.delete("1.0", "end")
        self.body_text.insert("1.0", "Selecione uma mensagem para visualizar o conteudo.")
        self.body_text.configure(state="disabled")

    def train_model(self) -> None:
        try:
            records = [
                email
                for email in self.repository.list_emails()
                if str(email.get("category", "")).strip() in CATEGORIES
            ]
            result = self.classifier.train_from_records(records)

            accuracy_text = "Validação separada não realizada"
            if result.accuracy is not None:
                accuracy_text = f"Acurácia de validação: {result.accuracy:.2f}"

            self.repository.log(
                "INFO",
                f"Modelo treinado com base local; registros {result.trained_rows}; {accuracy_text}",
            )
            messagebox.showinfo(
                "Treinamento concluído",
                "O modelo aprendeu com as categorias atualmente salvas na aplicação.\n\n"
                f"E-mails usados: {result.trained_rows}\n"
                f"{accuracy_text}\n\n"
                f"Arquivo salvo em:\n{result.model_path}",
            )
            self._set_status("Treinamento concluído", success=True)
        except Exception as exc:
            messagebox.showerror("Erro no treinamento", str(exc))

    def classify_all(self) -> None:
        try:
            self.classifier.ensure_model()
            emails = self.repository.list_emails()
            updated = 0
            for email in emails:
                prediction = self.classifier.predict(
                    str(email.get("subject", "")),
                    str(email.get("body", "")),
                    str(email.get("ocr_text", "") or ""),
                    sender=str(email.get("sender", "") or ""),
                )
                self.repository.update_classification(
                    int(email["id"]),
                    prediction.category,
                    prediction.confidence,
                )
                email["category"] = prediction.category
                email["confidence"] = prediction.confidence
                updated += 1
            self.repository.log("INFO", f"{updated} e-mails classificados")
            self.reload_emails()
            messagebox.showinfo("Classificação concluída", f"{updated} e-mails foram classificados.")
        except Exception as exc:
            messagebox.showerror("Erro ao classificar", str(exc))

    def apply_filter(self, value: str) -> None:
        self.current_filter = value
        self.filter_var.set(value)
        self._highlight_nav()
        self.refresh_emails()

    def reload_emails(self) -> None:
        self.email_cache = self.repository.list_email_summaries()
        self.refresh_emails()

    def _repair_legacy_gmail_imports(self) -> None:
        repaired = 0
        for email in self.repository.list_emails():
            if email.get("subject") != "Nenhum selecionado" or not email.get("body"):
                continue
            parsed = PyAutoGuiGmailReader._message_from_clipboard(str(email["body"]), int(email["id"]))
            if parsed.subject.startswith("Mensagem importada"):
                continue
            self.repository.update_email_content(int(email["id"]), parsed.sender, parsed.subject, parsed.body)
            repaired += 1
        if repaired:
            self.repository.log("INFO", f"{repaired} importacoes antigas do Gmail foram corrigidas")
            self.reload_emails()

    def _schedule_search_refresh(self) -> None:
        if self.search_after_id:
            self.after_cancel(self.search_after_id)
        self.search_after_id = self.after(180, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> None:
        self.search_after_id = None
        self.refresh_emails()

    def refresh_emails(self) -> None:
        self._update_counts()
        self._highlight_nav()

        for child in self.email_list.winfo_children():
            child.destroy()
        self.email_rows.clear()

        emails = self._visible_emails()
        self._update_folder_header(len(emails))
        if not emails:
            empty = ctk.CTkLabel(
                self.email_list,
                text="Nenhuma mensagem encontrada.",
                text_color=MUTED_TEXT,
            )
            empty.grid(row=0, column=0, sticky="ew", padx=18, pady=28)
            return

        for index, email in enumerate(emails[:MAX_RENDERED_EMAILS]):
            self._add_email_row(index, email)

        if len(emails) > MAX_RENDERED_EMAILS:
            notice = ctk.CTkLabel(
                self.email_list,
                text=f"Mostrando {MAX_RENDERED_EMAILS} de {len(emails)} mensagens. Use a busca ou filtros para refinar.",
                text_color="#a3a3a3",
            )
            notice.grid(row=MAX_RENDERED_EMAILS, column=0, sticky="ew", padx=18, pady=16)

    def _visible_emails(self) -> list[dict]:
        if self.current_filter == "Todas":
            emails = list(self.email_cache)
        else:
            emails = [email for email in self.email_cache if email.get("category") == self.current_filter]
        query = self.search_var.get().strip().lower()
        if not query:
            return emails

        filtered = []
        for email in emails:
            haystack = " ".join(
                [
                    str(email.get("sender", "")),
                    str(email.get("subject", "")),
                    str(email.get("body", "")),
                    str(email.get("ocr_text", "")),
                    str(email.get("category", "")),
                ]
            ).lower()
            if query in haystack:
                filtered.append(email)
        return filtered

    def _update_counts(self) -> None:
        emails = self.email_cache
        counts = {"Todas": len(emails), "Urgente": 0, "Trabalho": 0, "Pessoal": 0}
        for email in emails:
            category = email.get("category")
            if category in counts:
                counts[category] += 1

        for label, value in counts.items():
            if label in self.count_labels:
                self.count_labels[label].configure(text=str(value))

    def _update_folder_header(self, visible_count: int) -> None:
        title = "Caixa de entrada" if self.current_filter == "Todas" else self.current_filter
        self.folder_title.configure(text=title)
        suffix = "mensagem" if visible_count == 1 else "mensagens"
        self.folder_meta.configure(text=f"{visible_count} {suffix}")

    def _highlight_nav(self) -> None:
        for label, button in self.nav_buttons.items():
            selected = label == self.current_filter
            button.configure(
                fg_color="#303641" if selected else "transparent",
                hover_color="#303641" if selected else PANEL_HOVER,
                text_color=PRIMARY_TEXT if selected else MUTED_TEXT,
                font=ctk.CTkFont(size=14, weight="bold" if selected else "normal"),
            )

    def _add_email_row(self, index: int, email: dict) -> None:
        selected = self.selected_email and int(self.selected_email.get("id", -1)) == int(email.get("id", -2))
        row_color = "#252a32" if selected else PANEL_BG
        row = ctk.CTkFrame(self.email_list, fg_color=row_color, corner_radius=0)
        row.grid(row=index, column=0, sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        selection = ctk.CTkFrame(
            row, width=3, height=1, corner_radius=0,
            fg_color="#737b88" if selected else row_color,
        )
        selection.grid(row=0, column=0, rowspan=2, sticky="ns")
        self.email_rows[int(email["id"])] = (row, selection)
        sender = str(email.get("sender", "") or "Remetente nao informado")
        sender_label = ctk.CTkLabel(
            row, text=self._shorten(sender, 38), text_color=PRIMARY_TEXT,
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
        )
        sender_label.grid(row=0, column=1, sticky="ew", padx=(14, 8), pady=(12, 0))

        received = format_received_at(str(email.get("received_at") or email.get("created_at") or ""))
        date_label = ctk.CTkLabel(
            row, text=self._shorten(received, 18), text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=11), anchor="e",
        )
        date_label.grid(row=0, column=2, sticky="e", padx=(4, 14), pady=(12, 0))

        subject = self._shorten(str(email.get("subject", "") or "Sem assunto"), 48)
        preview_source = str(email.get("body", "") or email.get("ocr_text", "") or "")
        preview = self._shorten(preview_source.replace("\n", " "), 58)
        preview_label = ctk.CTkLabel(
            row, text=f"{subject}  -  {preview}" if preview else subject,
            text_color=MUTED_TEXT, anchor="w", font=ctk.CTkFont(size=12),
        )
        preview_label.grid(row=1, column=1, sticky="ew", padx=(14, 8), pady=(0, 12))

        category = str(email.get("category") or "Sem categoria")
        style = CATEGORY_STYLES.get(category, CATEGORY_STYLES["Sem categoria"])
        badge = ctk.CTkLabel(
            row, text=category, width=78, height=22, fg_color=style["bg"],
            text_color=style["fg"], corner_radius=3,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        badge.grid(row=1, column=2, sticky="e", padx=(4, 14), pady=(0, 10))
        for widget in (row, selection, sender_label, date_label, preview_label, badge):
            widget.bind("<Button-1>", lambda _event, payload=email: self.show_details(payload))

        divider = ctk.CTkFrame(row, height=1, fg_color="#2b2f36", corner_radius=0)
        divider.place(relx=0, rely=1, relwidth=1, anchor="sw")

    def _add_email_row_legacy(self, index: int, email: dict) -> None:
        selected = self.selected_email and int(self.selected_email.get("id", -1)) == int(email.get("id", -2))
        row = ctk.CTkFrame(self.email_list, fg_color="#242932" if selected else PANEL_BG, corner_radius=0)
        row.grid(row=index, column=0, sticky="ew")
        row.grid_columnconfigure(1, weight=1)
        row.bind("<Button-1>", lambda _event, payload=email: self.show_details(payload))

        avatar = self._avatar_text(email)
        avatar_label = ctk.CTkLabel(
            row,
            text=avatar,
            width=36,
            height=36,
            corner_radius=18,
            fg_color="#303641",
            text_color=PRIMARY_TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        avatar_label.grid(row=0, column=0, rowspan=2, padx=(16, 12), pady=14, sticky="n")
        avatar_label.bind("<Button-1>", lambda _event, payload=email: self.show_details(payload))

        sender = str(email.get("sender", "") or "Remetente não informado")
        sender_label = ctk.CTkLabel(
            row,
            text=self._shorten(sender, 34),
            text_color=PRIMARY_TEXT,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        sender_label.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(12, 0))
        sender_label.bind("<Button-1>", lambda _event, payload=email: self.show_details(payload))

        subject = self._shorten(str(email.get("subject", "")), 52)
        preview = self._shorten(str(email.get("body", "")).replace("\n", " "), 86)
        preview_label = ctk.CTkLabel(
            row,
            text=f"{subject} - {preview}" if preview else subject,
            text_color=MUTED_TEXT,
            anchor="w",
        )
        preview_label.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 12))
        preview_label.bind("<Button-1>", lambda _event, payload=email: self.show_details(payload))

        category = str(email.get("category") or "Sem categoria")
        style = CATEGORY_STYLES.get(category, CATEGORY_STYLES["Sem categoria"])
        badge = ctk.CTkLabel(
            row,
            text=category,
            width=86,
            height=24,
            fg_color=style["bg"],
            text_color=style["fg"],
            corner_radius=3,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        badge.grid(row=0, column=2, padx=(8, 14), pady=(12, 0), sticky="e")
        badge.bind("<Button-1>", lambda _event, payload=email: self.show_details(payload))

        open_button = ctk.CTkButton(
            row,
            text="Abrir",
            width=56,
            height=28,
            corner_radius=4,
            fg_color="#20242b",
            hover_color="#2c313a",
            text_color=PRIMARY_TEXT,
            border_width=1,
            border_color=BORDER,
            command=lambda payload=email: self.show_details(payload),
        )
        open_button.grid(row=0, column=3, rowspan=2, padx=(0, 14), pady=16)

        divider = ctk.CTkFrame(row, height=1, fg_color="#2b2f36")
        divider.grid(row=2, column=0, columnspan=4, sticky="ew", padx=(64, 0))

    def show_details(self, email: dict) -> None:
        full_email = self.repository.get_email(int(email["id"])) if email.get("id") is not None else None
        email = full_email or email
        self.selected_email = email
        category = str(email.get("category") or CATEGORIES[0])
        self.manual_category.configure(state="normal")
        self.manual_button.configure(state="normal")
        self.manual_category.set(category if category in CATEGORIES else CATEGORIES[0])
        style = CATEGORY_STYLES.get(category, CATEGORY_STYLES["Sem categoria"])
        self.detail_badge.configure(text=category, fg_color=style["bg"], text_color=style["fg"])
        self.detail_title.configure(text=str(email.get("subject", "") or "Sem assunto"))

        confidence = email.get("confidence")
        confidence_text = "sem indice"
        if confidence not in (None, ""):
            try:
                confidence_text = f"{float(confidence) * 100:.1f}%"
            except (TypeError, ValueError):
                pass
        self.detail_meta.configure(
            text=f"{email.get('sender') or 'Remetente nao informado'}\n"
            f"{email.get('received_at') or 'Data nao informada'}  |  Confianca {confidence_text}"
        )
        image_path = str(email.get("image_path") or "")
        self.capture_state.configure(
            text=capture_summary(
                str(email.get("capture_status") or "Somente texto"),
                str(email.get("ocr_status") or "Nao executado"),
                bool(image_path),
            )
        )
        self.body_text.configure(state="normal")
        self.body_text.delete("1.0", "end")
        self.body_text.insert(
            "1.0",
            build_extracted_text(str(email.get("body", "") or ""), str(email.get("ocr_text", "") or "")),
        )
        self.body_text.configure(state="disabled")
        self._show_reader_view("Mensagem" if image_path else "Texto extraido")
        self.after(30, lambda path=image_path: self._load_reader_image(path))
        self._highlight_selected_email()

    def _highlight_selected_email(self) -> None:
        selected_id = int(self.selected_email["id"]) if self.selected_email else -1
        for email_id, (row, selection) in self.email_rows.items():
            selected = email_id == selected_id
            row.configure(fg_color="#252a32" if selected else PANEL_BG)
            selection.configure(fg_color="#737b88" if selected else PANEL_BG)

    def _show_reader_view(self, view: str) -> None:
        self.reader_view = view
        showing_image = view == "Mensagem"
        if showing_image:
            self.body_text.grid_remove()
            self.image_view.grid()
        else:
            self.image_view.grid_remove()
            self.body_text.grid()
        self.message_tab.configure(
            fg_color="#2b3038" if showing_image else "transparent",
            text_color=PRIMARY_TEXT if showing_image else MUTED_TEXT,
        )
        self.text_tab.configure(
            fg_color="transparent" if showing_image else "#2b3038",
            text_color=MUTED_TEXT if showing_image else PRIMARY_TEXT,
        )

    def _load_reader_image(self, image_path: str) -> None:
        if not self.selected_email or str(self.selected_email.get("image_path") or "") != image_path:
            return
        if not image_path or not Path(image_path).is_file():
            self.reader_image = None
            self.image_label.configure(image=None, text="Esta mensagem nao possui captura visual.")
            return
        try:
            image = Image.open(image_path).convert("RGB")
            available = max(420, self.detail_panel.winfo_width() - 78)
            scale = min(1.0, available / image.width, 14_000 / image.height)
            size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            if size != image.size:
                image = image.resize(size, Image.Resampling.LANCZOS)
            self.reader_image = ctk.CTkImage(light_image=image, dark_image=image, size=size)
            self.image_label.configure(image=self.reader_image, text="")
        except (OSError, ValueError):
            self.reader_image = None
            self.image_label.configure(image=None, text="Nao foi possivel carregar a captura desta mensagem.")

    def _show_details_legacy(self, email: dict) -> None:
        full_email = self.repository.get_email(int(email["id"])) if email.get("id") is not None else None
        email = full_email or email
        self.selected_email = email
        category = str(email.get("category") or CATEGORIES[0])
        if category in CATEGORIES:
            self.manual_category.set(category)
        else:
            self.manual_category.set(CATEGORIES[0])

        style = CATEGORY_STYLES.get(category, CATEGORY_STYLES["Sem categoria"])
        self.detail_badge.configure(text=category, fg_color=style["bg"], text_color=style["fg"])
        self.detail_title.configure(text=str(email.get("subject", "")))

        confidence = email.get("confidence")
        confidence_text = "sem índice"
        if confidence not in (None, ""):
            try:
                confidence_text = f"{float(confidence) * 100:.1f}%"
            except (TypeError, ValueError):
                pass

        self.detail_meta.configure(
            text=f"De: {email.get('sender') or 'não informado'}\n"
            f"Recebido: {email.get('received_at') or 'não informado'}\n"
            f"Confiança da classificação: {confidence_text}"
        )
        self.body_text.configure(state="normal")
        self.body_text.delete("1.0", "end")
        self.body_text.insert("1.0", str(email.get("body", "")))
        self.body_text.configure(state="disabled")
    def save_manual_category(self) -> None:
        if not self.selected_email:
            messagebox.showinfo("Nenhuma mensagem selecionada", "Abra uma mensagem antes de alterar a categoria.")
            return
        category = self.manual_category.get()
        email_id = int(self.selected_email["id"])
        self.repository.update_classification(email_id, category, 1.0)
        self.repository.log("INFO", f"Categoria manual salva para e-mail {email_id}: {category}")
        for email in self.email_cache:
            if int(email["id"]) == email_id:
                email["category"] = category
                email["confidence"] = 1.0
                break
        self.refresh_emails()
        updated = dict(self.selected_email)
        updated["category"] = category
        updated["confidence"] = 1.0
        self.show_details(updated)
        messagebox.showinfo("Categoria salva", "A categoria foi atualizada.")

    @staticmethod
    def _avatar_text(email: dict) -> str:
        sender = str(email.get("sender", "") or "?").strip()
        if not sender or sender == "?":
            return "?"
        return sender[0].upper()

    @staticmethod
    def _shorten(text: str, limit: int) -> str:
        text = " ".join(text.split())
        if len(text) <= limit:
            return text
        return f"{text[: limit - 1].rstrip()}..."

    @staticmethod
    def _record_key(sender: str, subject: str, body: str) -> tuple[str, str, str]:
        return (
            " ".join(str(sender or "").lower().split()),
            " ".join(str(subject or "").lower().split()),
            " ".join(str(body or "").lower().split())[:220],
        )
