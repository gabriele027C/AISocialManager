import json
import logging
import re

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, THEME, BASE_DIR

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

MODEL = "gemini-2.5-flash"

THEMES_FILE = BASE_DIR / "themes.json"

JSON_SUFFIX = " Rispondi SEMPRE e SOLO con JSON valido, senza blocchi di codice markdown."

USER_PROMPT_TEMPLATE = (
    "{user_prompt} "
    "Rispondi con JSON valido (NO markdown, NO ```). Struttura esatta:\n"
    '{{"caption": "testo del post (max 2200 caratteri, usa \\n per gli a capo)", '
    '"hashtags": "#hashtag1 #hashtag2 ... (max 30 hashtag pertinenti)", '
    '"image_prompt": "prompt in inglese dettagliato per generare un\'immagine '
    'artistica e professionale coerente con il testo del post"}}'
)

MAX_RETRIES = 3


def _load_all_themes() -> dict:
    with open(THEMES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_theme(theme_id: str | None = None) -> dict:
    themes = _load_all_themes()
    tid = theme_id or THEME
    if tid not in themes:
        available = ", ".join(themes.keys())
        raise ValueError(f"Theme '{tid}' not found in themes.json. Available: {available}")
    return themes[tid]


def _clean_json(raw: str) -> str:
    """Strip markdown fences and fix common JSON issues from LLM output."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def get_current_theme() -> dict:
    """Return the default theme info."""
    theme = _get_theme()
    return {"id": THEME, "name": theme.get("name", THEME)}


def get_available_themes() -> list[dict]:
    """Return all available themes from themes.json."""
    themes = _load_all_themes()
    return [{"id": k, "name": v.get("name", k)} for k, v in themes.items()]


def generate_post_content(theme_id: str | None = None) -> dict:
    """Generate a single post's text content, hashtags and image prompt.

    Args:
        theme_id: Optional theme override. Falls back to THEME from .env.
    """
    theme = _get_theme(theme_id)
    active_theme = theme_id or THEME

    system_instruction = theme["system_instruction"] + JSON_SUFFIX
    user_prompt = USER_PROMPT_TEMPLATE.format(user_prompt=theme["user_prompt"])

    last_error: Exception | None = None
    raw = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.9,
                    max_output_tokens=2000,
                    response_mime_type="application/json",
                ),
            )

            raw = response.text
            if not raw:
                raise ValueError("Empty response from Gemini")

            cleaned = _clean_json(raw)
            data = json.loads(cleaned)

            if not all(k in data for k in ("caption", "hashtags", "image_prompt")):
                raise ValueError(f"Missing required keys in response: {list(data.keys())}")

            logger.info("Post content generated successfully (attempt %d, theme=%s)", attempt, active_theme)
            return {
                "caption": data["caption"],
                "hashtags": data["hashtags"],
                "image_prompt": data["image_prompt"],
            }

        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_error = exc
            logger.warning("Content generation parse error (attempt %d): %s — raw: %s", attempt, exc, raw[:200] if raw else "N/A")
        except Exception as exc:
            last_error = exc
            logger.error("Content generation API error (attempt %d): %s", attempt, exc)

    raise RuntimeError(f"Failed to generate post content after {MAX_RETRIES} attempts: {last_error}")
