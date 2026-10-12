from __future__ import annotations

from .app import EmailClassifierApp


def main() -> None:
    app = EmailClassifierApp()
    app.mainloop()


if __name__ == "__main__":
    main()
