from __future__ import annotations

from queue import Empty, Queue
from threading import Event, Thread
from tkinter import messagebox

import customtkinter as ctk

from .imap_importer import ImapImportError, ImapImporter, ImapSettings
from .config import get_imap_account_settings


class ImapDialog(ctk.CTkToplevel):
    """Network work stays in the worker; persistence and widgets stay in Tk."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Importar via IMAP — KingHost")
        self.geometry("540x640")
        self.resizable(False, False)
        self.transient(app)
        self.events = Queue()
        self.stop_event = Event()
        self.running = False
        self.imported = 0
        self.duplicates = 0
        self.save_error = False
        self.entries = {}
        saved = get_imap_account_settings()
        ctk.CTkLabel(self, text="Conecte sua caixa de e-mail", font=("Arial", 20, "bold")).pack(pady=(18, 8))
        ctk.CTkLabel(self, text="O navegador pode ficar fechado. Configure a conta em .env para não digitar sempre.").pack(pady=(0, 10))
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=24)
        form.grid_columnconfigure(1, weight=1)
        fields = [("host", "Servidor IMAP", saved.host), ("port", "Porta TLS", str(saved.port)),
                  ("username", "E-mail completo", saved.username), ("password", "Senha", saved.password),
                  ("folder", "Pasta", saved.folder), ("limit", "Últimas mensagens (1–200)", str(saved.limit))]
        for row, (key, label, default) in enumerate(fields):
            ctk.CTkLabel(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=8)
            entry = ctk.CTkEntry(form, show="•" if key == "password" else "", width=260)
            entry.grid(row=row, column=1, sticky="ew", pady=8)
            entry.insert(0, default)
            self.entries[key] = entry
        ctk.CTkLabel(self, text="Domínios em revenda podem usar imap.uni5.net.\n"
                     "A importação não marca mensagens como lidas.\n"
                     "Não importa anexos nem faz OCR nesta etapa.", wraplength=490).pack(pady=12)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=8)
        self.test_button = ctk.CTkButton(actions, text="Testar conexão", command=lambda: self.start(True), width=135)
        self.test_button.pack(side="left", padx=5)
        self.import_button = ctk.CTkButton(actions, text="Importar", command=lambda: self.start(False), width=110)
        self.import_button.pack(side="left", padx=5)
        self.stop_button = ctk.CTkButton(actions, text="Parar", command=self.stop, state="disabled", width=90)
        self.stop_button.pack(side="left", padx=5)
        self.status = ctk.CTkLabel(self, text="Informe os dados da conta para começar.", wraplength=485)
        self.status.pack(padx=20, pady=12)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.poll)

    def start(self, test_only):
        if self.running:
            return
        if self.app.gmail_import_running:
            messagebox.showinfo("Coleta em andamento", "Pare a coleta do Gmail primeiro.", parent=self)
            return
        try:
            settings = ImapSettings(
                host=self.entries["host"].get().strip(), port=int(self.entries["port"].get()),
                username=self.entries["username"].get().strip(), password=self.entries["password"].get(),
                folder=self.entries["folder"].get().strip(), limit=int(self.entries["limit"].get()),
            )
            if not settings.host or not settings.username or not settings.password or not settings.folder:
                raise ValueError("Preencha servidor, e-mail, senha e pasta.")
            if not 1 <= settings.limit <= 200 or not 1 <= settings.port <= 65535:
                raise ValueError("Use um limite entre 1 e 200 e uma porta válida.")
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Confira os dados", str(exc), parent=self)
            return
        self.running = True
        self.app.imap_import_running = True
        self.app._set_actions_enabled(False)
        self.imported = self.duplicates = 0
        self.save_error = False
        self.stop_event.clear()
        for entry in self.entries.values():
            entry.configure(state="disabled")
        self.test_button.configure(state="disabled")
        self.import_button.configure(state="disabled")
        self.stop_button.configure(state="normal", text="Parar")
        self.status.configure(text="Conectando com segurança...")
        Thread(target=self.worker, args=(settings, test_only), daemon=True).start()

    def worker(self, settings, test_only):
        try:
            importer = ImapImporter(settings, stop_event=self.stop_event,
                                    progress_callback=lambda message: self.events.put(("progress", message)))
            if test_only:
                importer.test_connection()
                self.events.put(("tested", None))
            else:
                def receive(record):
                    self.events.put(("record", record))
                    return True
                result = importer.collect(receive)
                self.events.put(("done", result))
        except ImapImportError as exc:
            self.events.put(("error", str(exc)))
        except Exception:
            self.events.put(("error", "Não foi possível concluir a operação IMAP."))

    def stop(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled", text="Parando...")
        self.status.configure(text="Parando. Uma operação de rede pode aguardar até o tempo limite.")

    def finish(self, text):
        self.running = False
        self.app.imap_import_running = False
        self.app._set_actions_enabled(self.app.classifier_ready)
        for entry in self.entries.values():
            entry.configure(state="normal")
        self.test_button.configure(state="normal")
        self.import_button.configure(state="normal")
        self.stop_button.configure(state="disabled", text="Parar")
        self.app.reload_emails()
        self.status.configure(text=text)

    def poll(self):
        if self.app.closing or not self.winfo_exists():
            self.stop_event.set()
            return
        try:
            for _ in range(10):
                kind, payload = self.events.get_nowait()
                if kind == "record" and not self.save_error:
                    try:
                        imported, duplicates = self.app._save_records([payload])
                        self.imported += imported
                        self.duplicates += duplicates
                    except Exception:
                        self.save_error = True
                        self.stop_event.set()
                elif kind == "progress" and not self.stop_event.is_set():
                    self.status.configure(text=str(payload))
                elif kind in ("done", "tested", "error"):
                    if self.save_error:
                        text = "Falha ao salvar/classificar. As mensagens já salvas foram preservadas."
                    elif kind == "error":
                        text = str(payload)
                    elif kind == "tested":
                        text = "Conexão confirmada. Clique em Importar para buscar as mensagens."
                    else:
                        text = "Importação interrompida." if payload.cancelled else "Importação concluída."
                        text += f" {payload.skipped_count} mensagens ignoradas."
                    if kind != "tested":
                        text += f" {self.imported} salvas; {self.duplicates} duplicadas."
                    self.finish(text)
        except Empty:
            pass
        self.after(100, self.poll)

    def close(self):
        if self.running:
            self.stop()
            return
        self.entries["password"].delete(0, "end")
        self.destroy()
