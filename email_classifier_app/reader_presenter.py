from __future__ import annotations

from datetime import datetime


def build_extracted_text(body: str, ocr_text: str) -> str:
    sections: list[str] = []
    if body.strip():
        sections.append(f"TEXTO DO E-MAIL\n{body.strip()}")
    if ocr_text.strip():
        sections.append(f"TEXTO ENCONTRADO NAS IMAGENS\n{ocr_text.strip()}")
    return "\n\n".join(sections) or "Nenhum texto foi encontrado nesta mensagem."


def capture_summary(capture_status: str, ocr_status: str, has_image: bool) -> str:
    capture = {
        "Completa": "Captura completa",
        "Parcial": "Captura parcial",
        "Somente texto": "Somente texto",
    }.get(capture_status, capture_status or "Somente texto")
    if not has_image:
        return capture
    ocr = {
        "Concluido": "OCR concluido",
        "Indisponivel": "OCR indisponivel",
        "Sem texto detectado": "OCR sem texto",
        "Nao executado": "OCR nao executado",
    }.get(ocr_status, ocr_status or "OCR nao executado")
    return f"{capture} | {ocr}"


def format_received_at(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value
