"""Compose text overlay slides on top of a background image.

Given a caption and a background image, produces one or more 1080x1080 images
with the text rendered on a semi-transparent overlay.  Long captions are split
into multiple slides at sentence boundaries so that each slide ends with
punctuation.  The character limit per slide (MAX_CHARS_PER_SLIDE) is kept in
sync with the frontend splitCaption() function.
"""

import logging
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import GENERATED_IMAGES_DIR

logger = logging.getLogger(__name__)

SLIDE_SIZE = (1080, 1080)
FONT_SIZE = 52
LINE_SPACING = 18
OVERLAY_COLOR = (0, 0, 0, 155)
TEXT_COLOR = (255, 255, 255)
PADDING_X = 80
PADDING_Y = 80
MAX_CHARS_PER_SLIDE = 220


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Try to load a clean sans-serif font, falling back to default."""
    candidates = [
        "C:/Windows/Fonts/segoeuil.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _split_into_slides(text: str, max_chars: int = MAX_CHARS_PER_SLIDE) -> list[str]:
    """Split caption into slide pages at sentence boundaries.

    Uses the same 220-char limit as the frontend splitCaption() so the
    number of slides always matches what the user sees in the preview.
    """
    if not text:
        return [""]

    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    sentences = re.findall(r"[^.!?]*[.!?]+", text)
    if not sentences:
        return [text]

    pages: list[str] = []
    current = ""

    for raw in sentences:
        s = raw.strip()
        if not s:
            continue
        candidate = (current + " " + s).strip() if current else s

        if len(candidate) > max_chars and current:
            pages.append(current.strip())
            current = s
        else:
            current = candidate

    if current.strip():
        last = current.strip()
        if not re.search(r"[.!?]$", last):
            last += "."
        pages.append(last)

    return pages if pages else [text]


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    line = ""

    for word in words:
        test = f"{line} {word}".strip()
        bbox = font.getbbox(test)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or [""]


def _render_slide(bg: Image.Image, text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    """Render a single slide: background + overlay + centered text."""
    slide = bg.copy().resize(SLIDE_SIZE, Image.LANCZOS)
    if slide.mode != "RGBA":
        slide = slide.convert("RGBA")

    overlay = Image.new("RGBA", SLIDE_SIZE, OVERLAY_COLOR)
    slide = Image.alpha_composite(slide, overlay)

    draw = ImageDraw.Draw(slide)
    usable_w = SLIDE_SIZE[0] - 2 * PADDING_X

    all_lines: list[str] = []
    for paragraph in text.split("\n"):
        wrapped = _wrap_text(paragraph, font, usable_w)
        all_lines.extend(wrapped)

    line_height = FONT_SIZE + LINE_SPACING
    total_h = line_height * len(all_lines) - LINE_SPACING
    y = (SLIDE_SIZE[1] - total_h) // 2

    for line in all_lines:
        bbox = font.getbbox(line)
        w = bbox[2] - bbox[0]
        x = (SLIDE_SIZE[0] - w) // 2

        for dx, dy in [(0, 3), (3, 0), (0, -1), (-1, 0), (2, 2)]:
            draw.text((x + dx, y + dy), line, fill=(0, 0, 0, 160), font=font)
        draw.text((x, y), line, fill=TEXT_COLOR, font=font)
        y += line_height

    return slide.convert("RGB")


def compose_slides(image_filename: str, caption: str) -> list[str]:
    """Create slide images with text overlaid on the background.

    Returns a list of file paths (filenames only, inside GENERATED_IMAGES_DIR).
    For a short caption, returns a single slide; for longer text, multiple slides.
    """
    bg_path = GENERATED_IMAGES_DIR / image_filename
    if not bg_path.exists():
        raise FileNotFoundError(f"Background image not found: {bg_path}")

    bg = Image.open(bg_path)
    font = _get_font(FONT_SIZE)
    pages = _split_into_slides(caption)

    stem = Path(image_filename).stem
    slide_paths: list[str] = []

    for i, page_text in enumerate(pages):
        slide = _render_slide(bg, page_text, font)
        if len(pages) == 1:
            fname = f"{stem}_slide.jpg"
        else:
            fname = f"{stem}_slide_{i + 1}.jpg"
        out_path = GENERATED_IMAGES_DIR / fname
        slide.save(out_path, "JPEG", quality=95)
        slide_paths.append(fname)
        logger.info("Composed slide %d/%d: %s", i + 1, len(pages), fname)

    return slide_paths
