from __future__ import annotations

from queue import Empty, Queue
from pathlib import Path
from email.utils import parseaddr
from threading import Event, Thread
from tkinter import Menu, filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from .config import DATA_DIR
from .database import JsonCacheRepository, MySQLRepository, create_repository
from .desktop_rpa import DesktopGmailImporter
from .gmail_rpa import GmailMessage
from .importer import load_emails_from_csv
from .labels import CATEGORIES, DEFAULT_TRAINING_CSV
from .reader_presenter import build_extracted_text, capture_summary, format_received_at
from .imap_dialog import ImapDialog
from .ui_theme import (
    APP_BG, BORDER, CATEGORY_STYLES, DECISION_LABELS, FONT,
    PRIMARY, PRIMARY_HOVER, SIDEBAR_BG, SIDEBAR_MUTED,
    SPACE, SURFACE, SURFACE_SOFT, TEXT, TEXT_MUTED,
)


MAX_RENDERED_EMAILS = 40
TOPBAR_BG = SURFACE
PANEL_BG = SURFACE
PANEL_HOVER = SURFACE_SOFT
PRIMARY_TEXT = TEXT
MUTED_TEXT = TEXT_MUTED


class EmailClassifierApp(ctk.CTk):
    def __init__(self, demo_dir: Path | None = None) -> None:
        super().__init__()
        self.demo_dir = demo_dir
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.title("Mail Desk – Demonstração" if demo_dir is not None else "Organizador de E-mails")
        self.geometry("1320x820")
        self.minsize(980, 640)
        self.configure(fg_color=APP_BG)

        self.repository: MySQLRepository | JsonCacheRepository | None = None
        self.storage_status = "Preparando armazenamento local..."
        self.classifier = None
        self.classifier_ready = False
        self.startup_events: Queue[tuple[str, object]] = Queue()
        self.startup_error: str | None = None
        self.closing = False
        self.email_total = 0
        self.filtered_total = 0
        self.visible_email_results: list[dict] = []
        self.search_generation = 0
        self.rendered_email_count = 0
        self.page_loading = False
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
        self.imap_import_running = False
        self.imap_dialog = None
        self.gmail_stop_event = Event()
        self.gmail_events: Queue[tuple[str, object]] = Queue()
        self.reader_image: ctk.CTkImage | None = None
        self.reader_view = "Mensagem"

        self._build_layout()
        self._set_status("Preparando dados e modelo…", success=True)
        self._set_actions_enabled(False)
        self._show_loading_state("Carregando suas mensagens…")
        self.after(0, self._start_background_startup)
        self.after(80, self._process_startup_events)
        self.after(150, self._process_gmail_events)
        self.protocol("WM_DELETE_WINDOW", self._close_window)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, minsize=188)
        self.grid_columnconfigure(1, minsize=340, weight=1)
        self.grid_columnconfigure(2, minsize=390, weight=1)
        self.grid_rowconfigure(0, minsize=72)
        self.grid_rowconfigure(1, weight=1)

        self._build_topbar()
        self._build_sidebar()
        self._build_message_list()
        self._build_reading_pane()
        self._set_reader_empty()

    def _build_topbar(self) -> None:
        self.topbar = ctk.CTkFrame(self, fg_color=TOPBAR_BG, corner_radius=0, height=64)
        self.topbar.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.topbar.grid_columnconfigure(1, weight=1)

        brand = ctk.CTkLabel(
            self.topbar,
            text="Mail Desk",
            text_color=TEXT,
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        )
        brand.grid(row=0, column=0, sticky="w", padx=(20, 18), pady=12)

        search_box = ctk.CTkFrame(self.topbar, fg_color=SURFACE_SOFT, corner_radius=10,
                                  border_width=1, border_color=BORDER)
        search_box.grid(row=0, column=1, sticky="ew", padx=(0, SPACE["md"]), pady=16)
        search_box.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(search_box, text="Buscar", text_color=TEXT_MUTED,
                     font=ctk.CTkFont(size=13)).grid(row=0, column=0, padx=(14, 8))
        self.search_entry = ctk.CTkEntry(
            search_box,
            textvariable=self.search_var,
            placeholder_text="Pesquisar e-mails",
            height=42,
            corner_radius=10,
            fg_color=SURFACE_SOFT,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
        )
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ctk.CTkButton(search_box, text="Limpar", width=56, fg_color="transparent",
                      text_color=TEXT_MUTED, hover_color="#e2e8f0", command=self._clear_search
                      ).grid(row=0, column=2, padx=8)
        self.search_entry.bind("<KeyRelease>", lambda _event: self._schedule_search_refresh())
        self.search_entry.bind("<Return>", lambda _event: self._run_scheduled_refresh())

        actions = ctk.CTkFrame(self.topbar, fg_color="transparent")
        actions.grid(row=0, column=2, sticky="e", padx=(0, SPACE["lg"]), pady=SPACE["md"])
        self.action_button = ctk.CTkButton(
            actions, text="Ações", command=self._show_action_menu, height=42, width=94,
            corner_radius=10, fg_color=SURFACE, hover_color=SURFACE_SOFT,
            border_width=1, border_color=BORDER, text_color=TEXT,
        )
        self.action_button.grid(row=0, column=0, padx=(0, SPACE["sm"]))
        self.imap_top_button = ctk.CTkButton(
            actions, text="Importar e-mails", command=self.import_imap, height=42,
            corner_radius=10, fg_color=PRIMARY, hover_color=PRIMARY_HOVER,
            text_color="#ffffff", font=ctk.CTkFont(size=FONT["body"], weight="bold"),
        )
        self.imap_top_button.grid(row=0, column=1)
        self.action_menu = Menu(self, tearoff=False, font=("Segoe UI", 10),
                                background=SURFACE, foreground=TEXT,
                                activebackground="#dbeafe", activeforeground=TEXT)
        self.action_menu.add_command(label="Carregar exemplos", command=self.import_sample_csv)
        self.action_menu.add_command(label="Classificar previsões", command=self.classify_all)
        self.action_menu.add_command(label="Treinar com rótulos revisados", command=self.train_model)
        self.action_menu.add_separator()
        self.action_menu.add_command(label="Importar CSV", command=self.import_csv)
        if self.demo_dir is None:
            self.action_menu.add_command(label="Importar do Gmail antigo…", command=self.import_gmail)
        self.action_menu.add_separator()
        self.action_menu.add_command(label="Limpar mensagens…", command=self.clear_emails)

    def _show_action_menu(self) -> None:
        x = self.action_button.winfo_rootx()
        y = self.action_button.winfo_rooty() + self.action_button.winfo_height()
        self.action_menu.tk_popup(x, y)

    def _set_actions_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in (self.action_button, self.imap_top_button, self.imap_button,
                       self.gmail_button, self.import_button):
            button.configure(state=state)
        if self.demo_dir is not None:
            self.imap_top_button.grid_remove()
            self.imap_button.configure(text="Importar CSV", command=self.import_csv, state=state)
        self.gmail_stop_button.configure(
            state="normal" if enabled and self.gmail_import_running else "disabled"
        )
        if hasattr(self, "action_menu"):
            menu_state = "normal" if enabled else "disabled"
            for index in range(self.action_menu.index("end") + 1):
                if self.action_menu.type(index) != "separator":
                    self.action_menu.entryconfigure(index, state=menu_state)

    def _build_sidebar(self) -> None:
        self.sidebar = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(10, weight=1)

        self.imap_button = ctk.CTkButton(
            self.sidebar, text="＋  Importar via IMAP", command=self.import_imap,
            height=46, corner_radius=10, fg_color=PRIMARY, hover_color=PRIMARY_HOVER,
            text_color="#ffffff", font=ctk.CTkFont(size=FONT["body"], weight="bold"),
        )
        self.imap_button.grid(row=0, column=0, sticky="ew", padx=SPACE["md"], pady=(SPACE["lg"], SPACE["sm"]))

        self.gmail_button = ctk.CTkButton(
            self.sidebar,
            text="Gmail (tela antiga)",
            command=self.import_gmail,
            height=34,
            corner_radius=8,
            fg_color="transparent",
            hover_color="#263244",
            text_color=SIDEBAR_MUTED,
            font=ctk.CTkFont(size=FONT["small"]),
        )
        # Legacy collection remains available in the Actions menu.

        self.gmail_stop_button = ctk.CTkButton(
            self.sidebar,
            text="Parar varredura",
            command=self.stop_gmail_import,
            height=32,
            corner_radius=8,
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            text_color="#ffffff",
            state="disabled",
        )


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


        mailbox_title = ctk.CTkLabel(
            self.sidebar,
            text="SUA CAIXA DE E-MAILS",
            text_color=SIDEBAR_MUTED,
            anchor="w",
            font=ctk.CTkFont(size=FONT["small"], weight="bold"),
        )
        mailbox_title.grid(row=4, column=0, sticky="ew", padx=SPACE["md"], pady=(SPACE["md"], SPACE["sm"]))

        for row, label in enumerate(["Todas", *CATEGORIES], start=5):
            self._add_nav_item(row, label)

        status_card = ctk.CTkFrame(
            self.sidebar,
            fg_color="#1e293b",
            corner_radius=12,
            border_width=0,
            border_color="#334155",
        )
        status_card.grid(row=11, column=0, sticky="ew", padx=SPACE["sm"], pady=(SPACE["sm"], SPACE["md"]))
        status_card.grid_columnconfigure(0, weight=1)

        self.storage_label = ctk.CTkLabel(
            status_card,
            text=self._friendly_storage_status(),
            text_color="#ffffff",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.storage_label.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))

        self.status_label = ctk.CTkLabel(
            status_card,
            text="Preparando...",
            text_color=SIDEBAR_MUTED,
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
        self.detail_panel = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0)
        self.detail_panel.grid(row=1, column=2, sticky="nsew")
        self.detail_panel.grid_columnconfigure(0, weight=1)
        self.detail_panel.grid_rowconfigure(5, weight=1)
        self.detail_panel.bind("<Configure>", self._resize_reader)

        self.reader_toolbar = ctk.CTkFrame(self.detail_panel, fg_color="transparent", corner_radius=0)
        self.reader_toolbar.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 0))
        self.reader_toolbar.grid_columnconfigure(1, weight=1)
        self.detail_badge = ctk.CTkLabel(
            self.reader_toolbar, text="", width=96, height=24, corner_radius=3,
            fg_color=SURFACE_SOFT, text_color=TEXT_MUTED,
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
            self.detail_panel, fg_color=SURFACE_SOFT, corner_radius=10,
            border_width=1, border_color=BORDER,
        )
        self.correction_bar = correction_bar
        correction_bar.grid(row=3, column=0, sticky="ew", padx=26, pady=(0, 14))
        correction_bar.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(
            correction_bar, text="Categoria", text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, padx=(14, 10), pady=10)
        self.manual_category = ctk.CTkOptionMenu(
            correction_bar, values=list(CATEGORIES), width=156, height=34, corner_radius=8,
            fg_color=SURFACE, button_color=PRIMARY, button_hover_color=PRIMARY_HOVER,
            dropdown_fg_color=SURFACE, dropdown_hover_color=SURFACE_SOFT,
            dropdown_text_color=TEXT, text_color=TEXT,
            state="disabled",
        )
        self.manual_category.grid(row=0, column=1, sticky="w", pady=10)
        self.manual_button = ctk.CTkButton(
            correction_bar, text="Salvar categoria", command=self.save_manual_category,
            width=132, height=34, corner_radius=8, fg_color=PRIMARY,
            hover_color=PRIMARY_HOVER, text_color="#ffffff",
            state="disabled",
        )
        self.manual_button.grid(row=0, column=3, sticky="e", padx=12, pady=10)

        tabs = ctk.CTkFrame(self.detail_panel, fg_color="transparent", corner_radius=0)
        self.reader_tabs = tabs
        tabs.grid(row=4, column=0, sticky="ew", padx=26)
        tabs.grid_columnconfigure(2, weight=1)
        self.message_tab = ctk.CTkButton(
            tabs, text="Captura", command=lambda: self._show_reader_view("Mensagem"),
            width=92, height=34, corner_radius=8, fg_color="#dbeafe",
            hover_color="#bfdbfe", text_color=PRIMARY,
        )
        self.message_tab.grid(row=0, column=0, padx=(0, 6))
        self.text_tab = ctk.CTkButton(
            tabs, text="Mensagem", command=lambda: self._show_reader_view("Texto extraido"),
            width=112, height=34, corner_radius=8, fg_color="transparent",
            hover_color=SURFACE_SOFT, text_color=TEXT_MUTED,
        )
        self.text_tab.grid(row=0, column=1)

        self.reader_content = ctk.CTkFrame(self.detail_panel, fg_color=SURFACE_SOFT, corner_radius=10)
        self.reader_content.grid(row=5, column=0, sticky="nsew", padx=26, pady=(10, 22))
        self.reader_content.grid_columnconfigure(0, weight=1)
        self.reader_content.grid_rowconfigure(0, weight=1)
        self.image_view = ctk.CTkScrollableFrame(
            self.reader_content, fg_color=SURFACE_SOFT, corner_radius=10,
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
            self.reader_content, wrap="word", fg_color=SURFACE, border_width=1,
            border_color=BORDER, text_color=TEXT, font=ctk.CTkFont(size=14),
        )
        self.body_text.grid(row=0, column=0, sticky="nsew")
        self.body_text.grid_remove()
        self.body_text.insert("1.0", "O conteudo da mensagem aparecera aqui.")
        self.body_text.configure(state="disabled")



    def _add_nav_item(self, row: int, label: str) -> None:
        button = ctk.CTkButton(
            self.sidebar,
            text=label,
            command=lambda item=label: self.apply_filter(item),
            height=38,
            corner_radius=3,
            fg_color="transparent",
            hover_color="#263449",
            text_color="#cbd5e1",
            anchor="w",
            font=ctk.CTkFont(size=14, weight="normal"),
        )
        button.grid(row=row, column=0, sticky="ew", padx=12, pady=1)
        self.nav_buttons[label] = button

        count = ctk.CTkLabel(button, text="0", text_color="#cbd5e1", width=34, fg_color="transparent")
        count.place(relx=0.94, rely=0.50, anchor="e")
        self.count_labels[label] = count

    def _show_loading_state(self, message: str) -> None:
        self.loading_label = ctk.CTkLabel(
            self.email_list, text=message, text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=FONT["body"]),
        )
        self.loading_label.grid(row=0, column=0, sticky="ew", padx=SPACE["lg"], pady=SPACE["xl"])
        self.loading_progress = ctk.CTkProgressBar(self.email_list, mode="indeterminate", height=4,
                                                   progress_color=PRIMARY)
        self.loading_progress.grid(row=1, column=0, sticky="ew", padx=SPACE["lg"], pady=SPACE["sm"])
        self.loading_progress.start()

    def _close_window(self) -> None:
        self.closing = True
        self.gmail_stop_event.set()
        if self.imap_dialog is not None:
            self.imap_dialog.stop_event.set()
        if self.search_after_id:
            try:
                self.after_cancel(self.search_after_id)
            except Exception:
                pass
        try:
            self.action_menu.unpost()
        except Exception:
            pass
        self.destroy()

    def _remove_loading_state(self) -> None:
        progress = getattr(self, "loading_progress", None)
        if progress is not None:
            progress.stop()
            progress.destroy()
            self.loading_progress = None
        label = getattr(self, "loading_label", None)
        if label is not None:
            label.destroy()
            self.loading_label = None

    def _start_background_startup(self) -> None:
        Thread(target=self._initialize_repository_and_model, daemon=True).start()

    def _initialize_repository_and_model(self) -> None:
        try:
            if self.demo_dir is None:
                repository, status = create_repository()
                model_path = None
            else:
                repository = JsonCacheRepository(self.demo_dir / "emails.json", self.demo_dir / "capturas")
                repository.connect()
                status = "Modo demonstração"
                model_path = self.demo_dir / "modelo.joblib"
            self.startup_events.put(("storage", (repository, status)))
            emails = repository.list_email_summaries()
            self.startup_events.put(("emails", emails))
            from .model import EmailClassifier
            classifier = EmailClassifier(model_path) if model_path is not None else EmailClassifier()
            classifier.ensure_model()
            self.startup_events.put(("model_ready", classifier))
        except Exception as exc:
            self.startup_events.put(("startup_error", str(exc)))

    def _process_startup_events(self) -> None:
        if self.closing:
            return
        try:
            while True:
                event, payload = self.startup_events.get_nowait()
                if event == "storage":
                    self.repository, self.storage_status = payload
                    self.storage_label.configure(text=self._friendly_storage_status())
                elif event == "emails":
                    self._remove_loading_state()
                    self.email_cache = payload
                    self.email_total = len(payload)
                    self.refresh_emails()
                elif event == "model_ready":
                    self.classifier = payload
                    self.classifier_ready = True
                    self._set_actions_enabled(True)
                    self._set_status("Pronto para importar e revisar mensagens", success=True)
                elif event == "startup_error":
                    self.startup_error = str(payload)
                    self._remove_loading_state()
                    self._set_status("Modelo indisponível. Use Ações para tentar novamente.", success=False)
                    self.action_button.configure(state="normal")
                    if not getattr(self, "recovery_added", False):
                        self.action_menu.add_command(label="Tentar carregar novamente", command=self._start_background_startup)
                        self.recovery_added = True
                elif event == "reload":
                    generation, payload = payload
                    if generation == self.search_generation:
                        self.email_cache = payload
                        self.email_total = len(payload)
                        self.refresh_emails()
                elif event == "search":
                    generation, query, offset, results, total = payload
                    if generation == self.search_generation and query == self.search_var.get().strip():
                        self.page_loading = False
                        if offset != len(self.visible_email_results) and offset != 0:
                            continue
                        if offset == 0:
                            self.visible_email_results = results
                        else:
                            self.visible_email_results.extend(results)
                        self.filtered_total = total
                        self._render_email_page()
        except Empty:
            pass
        self.after(80, self._process_startup_events)

    def _friendly_storage_status(self) -> str:
        if self.repository is None:
            return "Carregando armazenamento…"
        if isinstance(self.repository, MySQLRepository):
            return "Banco local conectado"
        if self.demo_dir is not None:
            return "Modo demonstração"
        return "Armazenamento local"

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

    def import_imap(self) -> None:
        if self.gmail_import_running:
            messagebox.showinfo("Coleta em andamento", "Pare a coleta do Gmail antes de conectar por IMAP.")
            return
        if self.imap_dialog is not None and self.imap_dialog.winfo_exists():
            self.imap_dialog.lift()
            self.imap_dialog.focus_force()
            return
        self.imap_dialog = ImapDialog(self)
        self.imap_dialog.lift()

    def import_gmail(self) -> None:
        if self.gmail_import_running or self.imap_import_running:
            return
        messagebox.showinfo(
            "Leitura do Gmail",
            "Deixe o Google Chrome aberto no Gmail, com a Caixa de Entrada visivel, "
            "a janela maximizada e o zoom em 100%.\n\n"
            "Durante a leitura, nao use o mouse ou o teclado.",
        )
        self.gmail_import_running = True
        self.gmail_stop_button.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        self.gmail_stop_event.clear()
        self.gmail_button.configure(state="disabled", text="Lendo Gmail...")
        self.gmail_stop_button.configure(state="normal")
        self._set_status("Preparando leitura do Gmail aberto...", success=True)
        Thread(target=self._collect_gmail_in_background, daemon=True).start()

    def stop_gmail_import(self) -> None:
        if self.gmail_import_running:
            self.gmail_stop_event.set()
            self.gmail_stop_button.configure(state="disabled", text="Parando...")
            self._set_status("Solicitando parada da varredura...", success=True)

    def _collect_gmail_in_background(self) -> None:
        def report_progress(message: str) -> None:
            self.gmail_events.put(("progress", message))

        try:
            importer = DesktopGmailImporter(
                max_messages=10,
                progress_callback=report_progress,
                stop_event=self.gmail_stop_event,
            )
            messages = importer.import_inbox()
            self.gmail_events.put(("success", (messages, importer.failure_count, importer.cancelled)))
        except Exception as exc:
            self.gmail_events.put(("error", str(exc)))

    def _process_gmail_events(self) -> None:
        if self.closing:
            return
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
        cancelled = False
        if isinstance(messages, tuple):
            messages, failure_count, *extra = messages
            cancelled = bool(extra and extra[0])
        records = [message.to_email_record() for message in messages if isinstance(message, GmailMessage)]
        try:
            imported, skipped = self._save_records(records)
            self.repository.log("INFO", f"{imported} e-mails importados do Gmail")
            self.reload_emails()
            self._set_status("Varredura interrompida" if cancelled else "Importacao do Gmail concluida", success=True)
            message = f"Varredura interrompida. {imported} e-mails coletados foram salvos." if cancelled else f"{imported} e-mails do Gmail foram importados e classificados."
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
            self.gmail_stop_button.configure(state="disabled", text="Parar varredura")
            self.gmail_stop_button.grid_remove()

    def _finish_gmail_import_error(self, error_message: str) -> None:
        self.gmail_import_running = False
        self.gmail_button.configure(state="normal", text="Importar do Gmail")
        self.gmail_stop_button.configure(state="disabled", text="Parar varredura")
        self.gmail_stop_button.grid_remove()
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
        if self.repository is None:
            raise RuntimeError("O armazenamento ainda não está pronto.")
        if self.classifier is None:
            raise RuntimeError("O modelo ainda está sendo preparado.")
        records = list(records)
        existing = self.repository.list_emails() if any(not record.source_key for record in records) else []
        source_keys = {email.get("source_key") for email in existing if email.get("source_key")}
        existing_keys = {
            self._record_key(
                str(email.get("sender", "")),
                str(email.get("subject", "")),
                str(email.get("body", "")),
            )
            for email in existing
        }
        for record in records:
            if record.category not in CATEGORIES:
                record.category = None
        if any(not record.category for record in records):
            self.classifier.ensure_model()

        imported = 0
        skipped = 0
        for record in records:
            key = self._record_key(record.sender, record.subject, record.body)
            if ((record.source_key in source_keys or self.repository.source_key_exists(record.source_key))
                    if record.source_key else key in existing_keys):
                skipped += 1
                continue
            if not record.category:
                prediction = self.classifier.predict(
                    record.subject, record.body, record.ocr_text, sender=record.sender
                )
                record.category = prediction.category
                record.confidence = prediction.confidence
                record.category_source = "automatic"
                record.decision_method = prediction.source
                record.decision_detail = prediction.detail
            elif record.category_source == "imported":
                record.decision_method = "imported"
            self.repository.save_email(record)
            existing_keys.add(key)
            if record.source_key:
                source_keys.add(record.source_key)
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
            "O modelo treinado será mantido. Para aprender com novas correções, use Treinar.",
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
        self.detail_badge.configure(text="", fg_color=SURFACE_SOFT, text_color=TEXT_MUTED)
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
        self._set_reader_empty()

    def train_model(self) -> None:
        try:
            records = [
                email
                for email in self.repository.list_emails()
                if str(email.get("category", "")).strip() in CATEGORIES
                and email.get("category_source") in ("manual", "imported")
            ]
            if len(records) < 6:
                raise ValueError("Revise e salve a categoria de pelo menos 6 e-mails, em pelo menos 2 categorias, "
                                 "ou importe um CSV rotulado. Previsões automáticas não entram no treinamento.")
            result = self.classifier.train_from_records(records)
            accuracy_text = "Validação separada não realizada"
            if result.accuracy is not None:
                accuracy_text = f"Acurácia de validação: {result.accuracy:.2f}"
            self.repository.log(
                "INFO", f"Modelo treinado com base local; registros {result.trained_rows}; {accuracy_text}"
            )
            self._set_status("Treinamento concluído", success=True)
            messagebox.showinfo(
                "Treinamento concluído",
                "O modelo aprendeu com as categorias atualmente salvas na aplicação.\n\n"
                f"E-mails usados: {result.trained_rows}\n{accuracy_text}\n\n"
                f"Arquivo salvo em:\n{result.model_path}",
            )
        except Exception as exc:
            messagebox.showerror("Erro no treinamento", str(exc))

    def classify_all(self) -> None:
        try:
            self.classifier.ensure_model()
            emails = self.repository.list_emails()
            updated = 0
            for email in emails:
                if email.get("category_source") in ("manual", "imported"):
                    continue
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
                    decision_method=prediction.source,
                    decision_detail=prediction.detail,
                )
                email["category"] = prediction.category
                email["confidence"] = prediction.confidence
                email["decision_method"] = prediction.source
                email["decision_detail"] = prediction.detail
                updated += 1
            self.repository.log("INFO", f"{updated} e-mails classificados")
            self.reload_emails()
            messagebox.showinfo("Classificação concluída", f"{updated} e-mails foram classificados.\n"
                                "Categorias revisadas e importadas de CSV foram preservadas.")
        except Exception as exc:
            messagebox.showerror("Erro ao classificar", str(exc))

    def apply_filter(self, value: str) -> None:
        self.current_filter = value
        self.filter_var.set(value)
        self._highlight_nav()
        self.refresh_emails()

    def reload_emails(self) -> None:
        if self.repository is None or self.closing:
            return
        self.search_generation += 1
        generation = self.search_generation
        repository = self.repository
        Thread(
            target=lambda: self.startup_events.put(("reload", (generation, repository.list_email_summaries()))),
            daemon=True,
        ).start()


    def _clear_search(self) -> None:
        self.search_var.set("")
        self._run_scheduled_refresh()

    def _schedule_search_refresh(self) -> None:
        if self.search_after_id:
            self.after_cancel(self.search_after_id)
        self.search_after_id = self.after(320, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> None:
        if self.search_after_id:
            self.after_cancel(self.search_after_id)
        self.search_after_id = None
        self.refresh_emails()

    def refresh_emails(self) -> None:
        self._update_counts()
        self._highlight_nav()
        if self.repository is None:
            return
        self.search_generation += 1
        self.page_loading = False
        query = self.search_var.get().strip()
        if query:
            generation = self.search_generation
            self.folder_meta.configure(text="Buscando em todo o conteúdo…")
            repository = self.repository
            category = self.current_filter
            Thread(target=self._search_messages_worker,
                   args=(repository, generation, query, category), daemon=True).start()
            return

        if self.current_filter == "Todas":
            emails = list(self.email_cache)
        else:
            emails = [email for email in self.email_cache if email.get("category") == self.current_filter]
        self.visible_email_results = emails[:MAX_RENDERED_EMAILS]
        self.filtered_total = len(emails)
        self._render_email_page()

    def _search_messages_worker(self, repository, generation: int, query: str, category: str,
                                offset: int = 0) -> None:
        try:
            results = repository.search_email_summaries(
                query=query, category=category, limit=MAX_RENDERED_EMAILS, offset=offset
            )
            total = repository.count_email_summaries(query=query, category=category) if offset == 0 else self.filtered_total
            self.startup_events.put(("search", (generation, query, offset, results, total)))
        except Exception:
            self.startup_events.put(("search", (generation, query, offset, [], 0)))

    def _render_email_page(self) -> None:
        for child in self.email_list.winfo_children():
            child.destroy()
        self.email_rows.clear()
        self.rendered_email_count = 0
        emails = self.visible_email_results
        self._update_folder_header(len(emails), self.filtered_total)
        if not emails:
            empty = ctk.CTkLabel(
                self.email_list,
                text="Nenhum e-mail corresponde à busca." if self.search_var.get().strip()
                else "Sua caixa está vazia. Importe mensagens para começar.",
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(size=FONT["body"]),
            )
            empty.grid(row=0, column=0, sticky="ew", padx=SPACE["lg"], pady=SPACE["xl"])
            return

        for index, email in enumerate(emails):
            self._add_email_row(index, email)
        self.rendered_email_count = len(emails)
        if self.filtered_total > self.rendered_email_count:
            load_more = ctk.CTkButton(
                self.email_list,
                text=f"Carregar mais 40  ·  {self.filtered_total - self.rendered_email_count} restantes",
                command=self._load_more_emails,
                height=40, corner_radius=10, fg_color="transparent",
                hover_color="#eff6ff", text_color=PRIMARY, border_width=1,
                border_color=BORDER,
            )
            load_more._maildesk_load_more = True
            load_more.grid(row=self.rendered_email_count, column=0, sticky="ew",
                           padx=SPACE["lg"], pady=SPACE["md"])

    def _load_more_emails(self) -> None:
        if self.page_loading:
            return
        for child in self.email_list.winfo_children():
            if getattr(child, "_maildesk_load_more", False):
                child.destroy()
        if self.search_var.get().strip():
            if self.repository is None:
                return
            self.page_loading = True
            Thread(target=self._search_messages_worker,
                   args=(self.repository, self.search_generation, self.search_var.get().strip(),
                         self.current_filter, self.rendered_email_count), daemon=True).start()
            return
        next_offset = self.rendered_email_count
        if self.current_filter == "Todas":
            emails = self.email_cache
        else:
            emails = [email for email in self.email_cache if email.get("category") == self.current_filter]
        next_page = emails[next_offset:next_offset + MAX_RENDERED_EMAILS]
        for index, email in enumerate(next_page, start=next_offset):
            self._add_email_row(index, email)
        self.visible_email_results.extend(next_page)
        self.rendered_email_count += len(next_page)
        self._update_folder_header(self.rendered_email_count, self.filtered_total)
        self._render_load_more_button()

    def _render_load_more_button(self) -> None:
        for child in self.email_list.winfo_children():
            if getattr(child, "_maildesk_load_more", False):
                child.destroy()
        if self.filtered_total <= self.rendered_email_count or self.search_var.get().strip():
            return
        button = ctk.CTkButton(
            self.email_list, text=f"Carregar mais 40  ·  {self.filtered_total - self.rendered_email_count} restantes",
            command=self._load_more_emails, height=40, corner_radius=10,
            fg_color="transparent", hover_color="#eff6ff", text_color=PRIMARY,
            border_width=1, border_color=BORDER,
        )
        button._maildesk_load_more = True
        button.grid(row=self.rendered_email_count, column=0, sticky="ew", padx=SPACE["lg"], pady=SPACE["md"])


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

    def _update_folder_header(self, visible_count: int, total: int | None = None) -> None:
        title = "Caixa de entrada" if self.current_filter == "Todas" else self.current_filter
        self.folder_title.configure(text=title)
        total = visible_count if total is None else total
        if total > visible_count:
            self.folder_meta.configure(text=f"Mostrando {visible_count} de {total} e-mails")
        else:
            suffix = "e-mail" if total == 1 else "e-mails"
            self.folder_meta.configure(text=f"{total} {suffix}")

    def _highlight_nav(self) -> None:
        for label, button in self.nav_buttons.items():
            selected = label == self.current_filter
            button.configure(
                fg_color="#223d68" if selected else "transparent",
                hover_color="#2b466e" if selected else "#263449",
                text_color="#ffffff" if selected else "#cbd5e1",
                font=ctk.CTkFont(size=14, weight="bold" if selected else "normal"),
            )

    def _add_email_row(self, index: int, email: dict) -> None:
        selected = self.selected_email and int(self.selected_email.get("id", -1)) == int(email.get("id", -2))
        row_color = "#eff6ff" if selected else PANEL_BG
        row = ctk.CTkFrame(self.email_list, fg_color=row_color, corner_radius=0)
        row.grid(row=index, column=0, sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        selection = ctk.CTkFrame(
            row, width=3, height=1, corner_radius=0,
            fg_color=PRIMARY if selected else row_color,
        )
        selection.grid(row=0, column=0, rowspan=3, sticky="ns")
        self.email_rows[int(email["id"])] = (row, selection)
        sender_raw = str(email.get("sender", "") or "")
        name, address = parseaddr(sender_raw)
        sender = name or address or "Remetente não informado"
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
            row, text=subject,
            text_color=MUTED_TEXT, anchor="w", font=ctk.CTkFont(size=12),
        )
        preview_label.grid(row=1, column=1, sticky="ew", padx=(14, 8), pady=(2, 0))
        body_preview = ctk.CTkLabel(row, text=preview, text_color=TEXT_MUTED, anchor="w",
                                   font=ctk.CTkFont(size=12))
        body_preview.grid(row=2, column=1, columnspan=2, sticky="ew", padx=14, pady=(0, 14))
        body_preview.bind("<Button-1>", lambda _event, payload=email: self.show_details(payload))

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

        divider = ctk.CTkFrame(row, height=1, fg_color=BORDER, corner_radius=0)
        divider.place(relx=0, rely=1, relwidth=1, anchor="sw")


    def _resize_reader(self, event) -> None:
        if hasattr(self, "detail_title"):
            available = max(280, min(620, (self.winfo_width() - 220) // 2 - 64))
            self.detail_title.configure(wraplength=available)
            self.detail_meta.configure(wraplength=available)

    def _set_reader_empty(self) -> None:
        if getattr(self, "empty_reader", None) is not None:
            self.empty_reader.destroy()
        for widget in (self.reader_toolbar, self.detail_title, self.detail_meta,
                       self.correction_bar, self.reader_tabs, self.reader_content):
            widget.grid_remove()
        self.empty_reader = ctk.CTkFrame(self.detail_panel, fg_color=SURFACE)
        self.empty_reader.grid(row=0, column=0, rowspan=6, sticky="nsew", padx=24, pady=24)
        self.empty_reader.grid_columnconfigure(0, weight=1)
        self.empty_reader.grid_rowconfigure(0, weight=1)
        self.empty_reader.grid_rowconfigure(4, weight=1)
        ctk.CTkLabel(self.empty_reader, text="✉", font=ctk.CTkFont(size=54), text_color=PRIMARY
                    ).grid(row=1, column=0, pady=(0, 16))
        ctk.CTkLabel(self.empty_reader, text="Seu espaço de leitura", text_color=TEXT,
                     font=ctk.CTkFont(size=24, weight="bold")).grid(row=2, column=0)
        ctk.CTkLabel(self.empty_reader, text="Selecione um e-mail para ler a mensagem,\nrevisar a categoria e ajudar o modelo a aprender.",
                     text_color=TEXT_MUTED, font=ctk.CTkFont(size=14), justify="center"
                     ).grid(row=3, column=0, pady=14)

    def show_details(self, email: dict) -> None:
        if getattr(self, "empty_reader", None) is not None:
            self.empty_reader.destroy()
            self.empty_reader = None
        for widget in (self.reader_toolbar, self.detail_title, self.detail_meta,
                       self.correction_bar, self.reader_tabs, self.reader_content):
            widget.grid()
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
        confidence_text = "sem indicador"
        if confidence not in (None, ""):
            try:
                confidence_text = f"{float(confidence) * 100:.1f}%"
            except (TypeError, ValueError):
                pass
        category_source = str(email.get("category_source") or "legacy")
        method = str(email.get("decision_method") or "unknown")
        source_label = DECISION_LABELS.get(method, DECISION_LABELS["unknown"])
        if method == "rule":
            confidence_label = "Indicador da regra"
        elif method == "manual":
            confidence_label = "Revisão humana"
            confidence_text = "confirmada"
        elif method == "imported":
            confidence_label = "CSV rotulado"
            confidence_text = "confirmado"
        elif method == "unknown":
            confidence_label = "Indicador indisponível"
            confidence_text = "não disponível"
            source_label = "Classificação antiga"
        else:
            confidence_label = "Confiança estimada pelo modelo"
        if category_source == "manual":
            guidance = "Revisado por você — pode ser usado no treinamento"
        elif category_source == "imported":
            guidance = "Rótulo importado — pode ser usado no treinamento"
        elif method == "unknown":
            guidance = "Origem antiga desconhecida — revise antes de treinar"
        else:
            guidance = "Previsão automática — revise antes de treinar"
        detail = str(email.get("decision_detail") or "") if method in ("model", "rule") else ""
        if not detail and method in ("model", "rule"):
            detail = "Motivo detalhado indisponível para esta previsão."
        self.detail_meta.configure(
            text=f"{email.get('sender') or 'Remetente não informado'}\n"
            f"{email.get('received_at') or 'Data não informada'}  |  {confidence_label}: {confidence_text}\n"
            f"{source_label} · {guidance}" + (f"\n{detail}" if detail else "")
        )
        image_path = str(email.get("image_path") or "")
        self.message_tab.configure(state="normal" if image_path else "disabled")
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
            row.configure(fg_color="#eff6ff" if selected else PANEL_BG)
            selection.configure(fg_color=PRIMARY if selected else PANEL_BG)

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
            fg_color="#dbeafe" if showing_image else "transparent",
            text_color=PRIMARY if showing_image else TEXT_MUTED,
        )
        self.text_tab.configure(
            fg_color="transparent" if showing_image else "#dbeafe",
            text_color=TEXT_MUTED if showing_image else PRIMARY,
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

    def save_manual_category(self) -> None:
        if not self.selected_email:
            messagebox.showinfo("Nenhuma mensagem selecionada", "Abra uma mensagem antes de alterar a categoria.")
            return
        category = self.manual_category.get()
        email_id = int(self.selected_email["id"])
        self.repository.update_classification(
            email_id, category, 1.0, source="manual", decision_method="manual"
        )
        self.repository.log("INFO", f"Categoria manual salva para e-mail {email_id}: {category}")
        for email in self.email_cache:
            if int(email["id"]) == email_id:
                email["category"] = category
                email["confidence"] = 1.0
                email["category_source"] = "manual"
                email["decision_method"] = "manual"
                email["decision_detail"] = ""
                break
        self.refresh_emails()
        updated = dict(self.selected_email)
        updated["category"] = category
        updated["confidence"] = 1.0
        self.show_details(updated)
        messagebox.showinfo("Categoria salva", "A categoria foi atualizada.")

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
