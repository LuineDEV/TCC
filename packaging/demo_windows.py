import os
import sys
from pathlib import Path

from email_classifier_app.app import EmailClassifierApp


def main() -> None:
    if "--smoke-test" in sys.argv:
        from tempfile import TemporaryDirectory
        from time import monotonic

        with TemporaryDirectory(prefix="mail-desk-release-") as directory:
            app = EmailClassifierApp(Path(directory))
            deadline = monotonic() + 25

            def check_startup() -> None:
                if app.classifier_ready:
                    app._close_window()
                elif app.startup_error or monotonic() >= deadline:
                    app._close_window()
                else:
                    app.after(100, check_startup)

            app.after(100, check_startup)
            app.mainloop()
            if not app.classifier_ready:
                (Path.cwd() / "maildesk-smoke-error.txt").write_text(
                    app.startup_error or "Tempo de inicialização excedido.", encoding="utf-8"
                )
                raise SystemExit(1)
        return
    base = Path(os.getenv("LOCALAPPDATA") or Path.home())
    EmailClassifierApp(base / "MailDeskTCC" / "Demonstracao").mainloop()


if __name__ == "__main__":
    main()
