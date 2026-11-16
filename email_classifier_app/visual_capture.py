from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class CaptureResult:
    image_path: str | None
    status: str
    frame_count: int
    reason: str = ""


def _comparison_array(image: Image.Image, width: int = 240) -> np.ndarray:
    gray = image.convert("L")
    if gray.width > width:
        height = max(1, round(gray.height * width / gray.width))
        gray = gray.resize((width, height), Image.Resampling.BILINEAR)
    margin = max(1, gray.width // 12)
    return np.asarray(gray, dtype=np.float32)[:, margin:-margin]


def image_difference(first: Image.Image, second: Image.Image) -> float:
    if first.size != second.size:
        second = second.resize(first.size, Image.Resampling.BILINEAR)
    left = _comparison_array(first)
    right = _comparison_array(second)
    return float(np.mean(np.abs(left - right)))


def find_vertical_overlap(previous: Image.Image, current: Image.Image) -> int:
    """Retorna a sobreposicao mais provavel; zero evita descartar conteudo incerto."""
    if previous.width != current.width:
        current = current.resize((previous.width, current.height), Image.Resampling.BILINEAR)
    previous_data = _comparison_array(previous)
    current_data = _comparison_array(current)
    scale = previous_data.shape[0] / previous.height
    minimum = max(24, int(min(previous.height, current.height) * 0.12))
    maximum = int(min(previous.height, current.height) * 0.82)
    candidates = range(minimum, maximum + 1, 4)
    best_overlap = 0
    best_score = float("inf")
    for overlap in candidates:
        scaled = max(2, round(overlap * scale))
        left = previous_data[-scaled:]
        right = current_data[:scaled]
        score = float(np.mean(np.abs(left - right)))
        if score < best_score:
            best_score = score
            best_overlap = overlap

    start = max(minimum, best_overlap - 4)
    end = min(maximum, best_overlap + 4)
    for overlap in range(start, end + 1):
        scaled = max(2, round(overlap * scale))
        score = float(np.mean(np.abs(previous_data[-scaled:] - current_data[:scaled])))
        if score < best_score:
            best_score = score
            best_overlap = overlap
    return best_overlap if best_score <= 18.0 else 0


def stitch_frames(frames: list[Image.Image], max_height: int = 30_000) -> Image.Image:
    if not frames:
        raise ValueError("E necessario ao menos um quadro para montar a captura.")
    width = frames[0].width
    normalized = [frame if frame.width == width else frame.resize((width, frame.height)) for frame in frames]
    pieces = [normalized[0]]
    total_height = normalized[0].height
    for previous, current in zip(normalized, normalized[1:]):
        overlap = find_vertical_overlap(previous, current)
        piece = current.crop((0, overlap, current.width, current.height))
        remaining = max_height - total_height
        if remaining <= 0:
            break
        if piece.height > remaining:
            piece = piece.crop((0, 0, piece.width, remaining))
        pieces.append(piece)
        total_height += piece.height
    result = Image.new("RGB", (width, total_height), "white")
    y = 0
    for piece in pieces:
        result.paste(piece.convert("RGB"), (0, y))
        y += piece.height
    return result


class ScrollableCapture:
    def __init__(
        self,
        gui,
        output_dir: Path,
        max_frames: int = 30,
        max_height: int = 30_000,
        stable_frames: int = 2,
        scroll_amount: int = -18,
        settle_seconds: float = 0.32,
    ) -> None:
        self.gui = gui
        self.output_dir = output_dir
        self.max_frames = max_frames
        self.max_height = max_height
        self.stable_frames = stable_frames
        self.scroll_amount = scroll_amount
        self.settle_seconds = settle_seconds

    def capture(
        self,
        name: str,
        region: tuple[int, int, int, int],
        scroll_point: tuple[int, int],
        stop_event: Event | None = None,
    ) -> CaptureResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        frames = [self.gui.screenshot(region=region).convert("RGB")]
        unchanged = 0
        status = "Parcial"
        reason = "Limite de seguranca atingido."
        self.gui.moveTo(*scroll_point, duration=0.1)

        cancelled = False
        while len(frames) < self.max_frames:
            if stop_event is not None and stop_event.is_set():
                cancelled = True
                status = "Interrompida"
                reason = "Captura interrompida pelo usuario."
                break
            press = getattr(self.gui, "press", None)
            if callable(press):
                press("pagedown")
            else:
                self.gui.scroll(self.scroll_amount)
            self.gui.sleep(self.settle_seconds)
            if stop_event is not None and stop_event.is_set():
                cancelled = True
                status = "Interrompida"
                reason = "Captura interrompida pelo usuario."
                break
            current = self.gui.screenshot(region=region).convert("RGB")
            if image_difference(frames[-1], current) <= 1.5:
                if unchanged == 0 and callable(press):
                    self.gui.scroll(self.scroll_amount)
                    self.gui.sleep(0.22)
                    fallback = self.gui.screenshot(region=region).convert("RGB")
                    if image_difference(frames[-1], fallback) > 1.5:
                        frames.append(fallback)
                        continue
                unchanged += 1
                if unchanged >= self.stable_frames:
                    status = "Completa"
                    reason = "Fim da mensagem detectado."
                    break
                continue
            unchanged = 0
            frames.append(current)

        stitched = stitch_frames(frames, self.max_height)
        if stitched.height >= self.max_height and status not in ("Completa", "Interrompida"):
            reason = "Limite de altura atingido."
        path = self.output_dir / f"{name}.png"
        stitched.save(path, format="PNG", optimize=True)
        return CaptureResult(str(path), status, len(frames), reason)
