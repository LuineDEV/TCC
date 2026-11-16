"""Small visual system shared by the native CustomTkinter interface."""

APP_BG = "#f4f6f9"
SURFACE = "#ffffff"
SURFACE_SOFT = "#f8fafc"
SIDEBAR_BG = "#111827"
SIDEBAR_MUTED = "#a7b2c2"
TEXT = "#111827"
TEXT_MUTED = "#5b6677"
BORDER = "#e5e9f0"
PRIMARY = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"
SUCCESS = "#15803d"
DANGER = "#b91c1c"
WARNING = "#a16207"

CATEGORY_STYLES = {
    "Urgente": {"bg": "#fee2e2", "fg": "#991b1b", "border": "#fecaca", "icon": "!"},
    "Trabalho": {"bg": "#dbeafe", "fg": "#1e40af", "border": "#bfdbfe", "icon": "▣"},
    "Pessoal": {"bg": "#dcfce7", "fg": "#166534", "border": "#bbf7d0", "icon": "●"},
    "Sem categoria": {"bg": "#f1f5f9", "fg": "#475569", "border": "#e2e8f0", "icon": "·"},
}

DECISION_LABELS = {
    "rule": "Regra automática",
    "model": "Modelo estatístico",
    "manual": "Revisado por você",
    "imported": "Rótulo do CSV",
    "unknown": "Origem desconhecida; revise",
}

SPACE = {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32}
FONT = {"small": 12, "body": 14, "subtitle": 16, "title": 22}
