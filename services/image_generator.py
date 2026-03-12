import logging
import time

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GENERATED_IMAGES_DIR

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

MAX_RETRIES = 2

SAFETY_PREFIX = (
    "Create a beautiful, artistic, professional photograph or illustration. "
    "No text, no words, no letters, no watermarks. "
)


def generate_image(prompt: str, post_id: int | None = None) -> str:
    """Generate an HD image with Gemini Imagen and save it locally.

    Returns the filename (relative to generated_images/).
    """
    last_error: Exception | None = None
    current_prompt = SAFETY_PREFIX + prompt

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=current_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/png",
                ),
            )

            if not response.generated_images:
                raise RuntimeError("No images returned by Imagen")

            image_bytes = response.generated_images[0].image.image_bytes
            filename = f"post_{post_id or 0}_{int(time.time())}.png"
            filepath = GENERATED_IMAGES_DIR / filename
            filepath.write_bytes(image_bytes)

            logger.info("Image generated and saved: %s (attempt %d)", filename, attempt)
            return filename

        except Exception as exc:
            last_error = exc
            logger.warning("Image generation error (attempt %d): %s", attempt, exc)
            if "safety" in str(exc).lower() or "block" in str(exc).lower():
                current_prompt = (
                    SAFETY_PREFIX
                    + "An abstract, artistic representation inspired by personal growth and inner peace. "
                    + "Soft colors, ethereal atmosphere, professional quality."
                )

    raise RuntimeError(f"Failed to generate image after {MAX_RETRIES} attempts: {last_error}")


def delete_image(filename: str) -> None:
    """Remove an image file from the generated_images directory."""
    filepath = GENERATED_IMAGES_DIR / filename
    if filepath.exists():
        filepath.unlink()
        logger.info("Deleted image: %s", filename)
