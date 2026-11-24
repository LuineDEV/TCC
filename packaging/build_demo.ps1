$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $root
try {
    $python = if (Test-Path ".venv/Scripts/python.exe") { ".venv/Scripts/python.exe" } else { "python" }
    $samples = Join-Path $root "data/sample_emails.csv"
    $demo = Join-Path $root "data/demonstracao_sem_rotulo.csv"
    & $python -m PyInstaller --noconfirm --windowed --name MailDesk --paths $root `
        --distpath output/entrega/build --workpath tmp/entrega_build --specpath tmp `
        --add-data "$($samples):data" --add-data "$($demo):data" `
        --exclude-module rapidocr --exclude-module onnxruntime --exclude-module torch `
        --exclude-module matplotlib --exclude-module IPython --exclude-module cv2 `
        packaging/demo_windows.py
    if ($LASTEXITCODE -ne 0) { throw "Falha ao empacotar o Mail Desk." }
} finally {
    Pop-Location
}
