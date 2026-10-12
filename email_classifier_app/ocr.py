from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


class LocalOcr:
    """OCR local com inicializacao tardia para nao atrasar a abertura do aplicativo."""

    def __init__(self, engine=None, tile_height: int = 1600) -> None:
        self.engine = engine
        self.tile_height = tile_height

    def _get_engine(self):
        if self.engine is not None:
            return self.engine
        from rapidocr import RapidOCR

        self.engine = RapidOCR()
        return self.engine

    def extract(self, image_path: str | Path) -> str:
        image = Image.open(image_path).convert("RGB")
        engine = self._get_engine()
        lines: list[str] = []
        overlap = 80
        start = 0
        while start < image.height:
            end = min(image.height, start + self.tile_height)
            tile = np.asarray(image.crop((0, start, image.width, end)))
            result = engine(tile)
            texts = getattr(result, "txts", None)
            if texts is None and isinstance(result, tuple) and result:
                legacy = result[0] or []
                texts = [item[1] for item in legacy if len(item) > 1]
            for text in texts or []:
                clean = " ".join(str(text).split())
                if clean and (not lines or clean != lines[-1]):
                    lines.append(clean)
            if end >= image.height:
                break
            start = end - overlap
        return "\n".join(lines)
