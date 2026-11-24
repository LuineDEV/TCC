"""Build and verify the Windows x64 demonstration ZIP with Python 3.12."""

import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from nltk.data import find


ROOT = Path(__file__).resolve().parent.parent
DEPENDENCIES = (
    "customtkinter==5.2.2", "mysql-connector-python==9.3.0", "pandas==3.0.0",
    "scikit-learn==1.8.0", "numpy==2.4.1", "scipy==1.17.1", "joblib==1.5.3",
    "nltk==3.9.4", "pyautogui==0.9.54", "pyperclip==1.11.0", "Pillow==11.2.1",
)
SAMPLES = ("sample_emails.csv", "demonstracao_sem_rotulo.csv")


def assemble(package: Path, compiler: Path) -> None:
    runtime = package / "_internal"
    runtime.mkdir(parents=True)
    base = Path(sys.base_prefix)
    for name in (
        "python.exe", "pythonw.exe", "python312.dll", "python3.dll",
        "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt",
    ):
        shutil.copy2(base / name, runtime)
    for name in ("DLLs", "tcl", "Lib"):
        shutil.copytree(
            base / name, runtime / name,
            ignore=shutil.ignore_patterns("site-packages", "__pycache__", "test", "tests", "idlelib", "tkintertest"),
        )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-compile",
         "--target", str(runtime / "Lib" / "site-packages"), *DEPENDENCIES],
        check=True,
    )
    (runtime / "python312._pth").write_text(".\nDLLs\nLib\nLib\\site-packages\n", encoding="ascii")
    shutil.copytree(
        ROOT / "email_classifier_app", runtime / "email_classifier_app",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (runtime / "data").mkdir()
    for name in SAMPLES:
        shutil.copy2(ROOT / "data" / name, runtime / "data")
    shutil.copy2(ROOT / "data" / SAMPLES[1], package)
    shutil.copy2(ROOT / "packaging" / "LEIA-ME.txt", package)
    shutil.copy2(ROOT / "packaging" / "demo_windows.py", runtime)
    corpus = runtime / "nltk_data" / "corpora" / "stopwords"
    corpus.mkdir(parents=True)
    for name in ("portuguese", "README"):
        with find(f"corpora/stopwords/{name}").open() as source, (corpus / name).open("wb") as target:
            shutil.copyfileobj(source, target)
    subprocess.run(
        [str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/codepage:65001",
         f"/out:{package / 'MailDesk.exe'}", "/reference:System.Windows.Forms.dll",
         str(ROOT / "packaging" / "launcher.cs")],
        check=True,
    )


def verify(archive_path: Path, folder: Path, windows: Path) -> None:
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Falha na verificação de integridade do ZIP.")
        archive.extractall(folder)
    extracted = folder / "MailDesk"
    env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("PYTHON", "IMAP_", "DB_", "NLTK_"))
    }
    env["PATH"] = str(windows / "System32")
    result = subprocess.run(
        [str(extracted / "MailDesk.exe"), "--smoke-test"], cwd=extracted, env=env, timeout=50,
    )
    if result.returncode:
        diagnosis = extracted / "maildesk-smoke-error.txt"
        raise RuntimeError(diagnosis.read_text(encoding="utf-8") if diagnosis.exists() else "Falha na abertura.")


def main() -> None:
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise SystemExit("Use o Python 3.12 de 64 bits no Windows.")
    windows = Path(os.environ["WINDIR"])
    compiler = windows / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    out = ROOT / "output" / "entrega"
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="mail-desk-build-", dir=out) as directory:
        work = Path(directory)
        package = work / "MailDesk"
        assemble(package, compiler)
        archive_path = work / "MailDesk_Demo_Windows_x64.zip"
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED, compresslevel=5) as archive:
            for item in sorted(package.rglob("*")):
                if item.is_file():
                    archive.write(item, item.relative_to(work).as_posix())
        verify(archive_path, work / "verify", windows)
        final = out / archive_path.name
        archive_path.replace(final)
    print(f"ZIP de demonstração verificado: {final}")


if __name__ == "__main__":
    main()
