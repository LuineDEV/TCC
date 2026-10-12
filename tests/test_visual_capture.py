from pathlib import Path

from PIL import Image

from email_classifier_app.visual_capture import ScrollableCapture, find_vertical_overlap, stitch_frames
from email_classifier_app.ocr import LocalOcr


def striped_image(height: int, offset: int = 0) -> Image.Image:
    image = Image.new("RGB", (120, height), "white")
    pixels = image.load()
    for y in range(height):
        value = (y + offset) % 256
        for x in range(120):
            pixels[x, y] = (value, (value * 3) % 256, (value * 7) % 256)
    return image


def test_find_vertical_overlap_and_stitch_preserve_only_new_content():
    full = striped_image(300)
    first = full.crop((0, 0, 120, 200))
    second = full.crop((0, 100, 120, 300))

    overlap = find_vertical_overlap(first, second)
    stitched = stitch_frames([first, second])

    assert 96 <= overlap <= 104
    assert stitched.size == (120, 300)


class CaptureGui:
    PAUSE = 0

    def __init__(self, frames: list[Image.Image]) -> None:
        self.frames = frames
        self.screenshot_index = 0
        self.clicks = []
        self.scrolls = []
        self.keys = []

    def screenshot(self, region):
        index = min(self.screenshot_index, len(self.frames) - 1)
        self.screenshot_index += 1
        return self.frames[index].copy()

    def moveTo(self, x, y, duration=0):
        return None

    def scroll(self, amount):
        self.scrolls.append(amount)

    def press(self, key):
        self.keys.append(key)

    def sleep(self, seconds):
        return None


def test_scroll_capture_stops_after_two_unchanged_frames_without_clicking(tmp_path: Path):
    frame = striped_image(180)
    gui = CaptureGui([frame, frame, frame])
    capture = ScrollableCapture(gui=gui, output_dir=tmp_path, stable_frames=2)

    result = capture.capture("message", region=(0, 0, 120, 180), scroll_point=(60, 100))

    assert result.status == "Completa"
    assert result.frame_count == 1
    assert Path(result.image_path).exists()
    assert gui.clicks == []
    assert gui.keys == ["pagedown", "pagedown"]
    assert gui.scrolls == [-18]


def test_scroll_capture_marks_result_partial_at_safety_limit(tmp_path: Path):
    frames = [striped_image(180, offset=i * 31) for i in range(5)]
    gui = CaptureGui(frames)
    capture = ScrollableCapture(gui=gui, output_dir=tmp_path, max_frames=3)

    result = capture.capture("limited", region=(0, 0, 120, 180), scroll_point=(60, 100))

    assert result.status == "Parcial"
    assert result.frame_count == 3
    assert "limite" in result.reason.lower()


class FakeOcrResult:
    txts = ["PROMOCAO", "50% de desconto"]


def test_local_ocr_extracts_text_from_image_tiles(tmp_path: Path):
    path = tmp_path / "visual.png"
    Image.new("RGB", (200, 100), "white").save(path)
    ocr = LocalOcr(engine=lambda _image: FakeOcrResult())

    text = ocr.extract(path)

    assert text == "PROMOCAO\n50% de desconto"
