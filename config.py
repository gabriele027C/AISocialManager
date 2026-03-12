import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Gemini (text generation)
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# Black Forest Labs — FLUX.1 (image generation)
BFL_API_KEY: str = os.getenv("BFL_API_KEY", "")

# Meta / Facebook Graph API
META_APP_ID: str = os.getenv("META_APP_ID", "")
META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
META_ACCESS_TOKEN: str = os.getenv("META_ACCESS_TOKEN", "")
FACEBOOK_PAGE_ID: str = os.getenv("FACEBOOK_PAGE_ID", "")
INSTAGRAM_BUSINESS_ACCOUNT_ID: str = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")

# Telegram
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# Server
APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

# Theme
THEME: str = os.getenv("THEME", "crescita_personale")

# Database
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./storylab.db")

# Paths
GENERATED_IMAGES_DIR: Path = BASE_DIR / "generated_images"
STATIC_DIR: Path = BASE_DIR / "static"
